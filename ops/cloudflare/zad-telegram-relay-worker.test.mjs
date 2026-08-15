import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const workerSource = await readFile(
  new URL("./zad-telegram-relay-worker.js", import.meta.url),
  "utf8"
);
const workerModuleUrl = `data:text/javascript;base64,${Buffer.from(
  workerSource
).toString("base64")}`;
const worker = (await import(workerModuleUrl)).default;

const env = {
  RELAY_SECRET: "relay-secret",
  TELEGRAM_BOT_TOKEN: "bot-token",
  TELEGRAM_WEBHOOK_SECRET: "webhook-secret",
};

function json(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function outboundRequest(payload, authorization = "Bearer relay-secret") {
  return new Request("https://relay.example/", {
    method: "POST",
    headers: {
      Authorization: authorization,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

function webhookRequest(text, options = {}) {
  const fromId = String(options.fromId ?? "101");
  const chatId = String(options.chatId ?? fromId);
  const chatType = options.chatType ?? "private";
  const secret = options.secret ?? "webhook-secret";

  return new Request("https://relay.example/telegram-webhook", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Bot-Api-Secret-Token": secret,
    },
    body: JSON.stringify({
      message: {
        from: { id: fromId },
        chat: { id: chatId, type: chatType },
        text,
      },
    }),
  });
}

async function withFetch(mock, callback) {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = mock;
  try {
    return await callback();
  } finally {
    globalThis.fetch = originalFetch;
  }
}

function requestPayload(call) {
  return JSON.parse(call.options.body);
}

test("outbound relay rejects an invalid secret before Telegram", async () => {
  let fetchCalls = 0;
  const response = await withFetch(
    async () => {
      fetchCalls += 1;
      return json({ ok: true });
    },
    () =>
      worker.fetch(
        outboundRequest(
          { text: "lead", chat_ids: ["101"] },
          "Bearer wrong-secret"
        ),
        env
      )
  );

  assert.equal(response.status, 401);
  assert.equal(fetchCalls, 0);
});

test("outbound relay requires an explicit recipient list", async () => {
  let fetchCalls = 0;
  const response = await withFetch(
    async () => {
      fetchCalls += 1;
      return json({ ok: true });
    },
    () => worker.fetch(outboundRequest({ text: "lead" }), env)
  );

  assert.equal(response.status, 400);
  assert.equal((await response.json()).error, "Invalid chat IDs");
  assert.equal(fetchCalls, 0);
});

test("outbound relay deduplicates recipients and fans out", async () => {
  const calls = [];
  const response = await withFetch(
    async (url, options) => {
      calls.push({ url: String(url), options });
      return json({ ok: true });
    },
    () =>
      worker.fetch(
        outboundRequest({
          text: "lead",
          chat_ids: ["101", 202, "101"],
        }),
        env
      )
  );

  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { ok: true, delivered: 2 });
  assert.deepEqual(
    calls.map((call) => requestPayload(call).chat_id),
    ["101", "202"]
  );
});

test("outbound relay reports partial Telegram failure", async () => {
  const response = await withFetch(
    async (_url, options) => {
      const payload = JSON.parse(options.body);
      return payload.chat_id === "202"
        ? json({ ok: false }, 400)
        : json({ ok: true });
    },
    () =>
      worker.fetch(
        outboundRequest({ text: "lead", chat_ids: ["101", "202"] }),
        env
      )
  );

  assert.equal(response.status, 502);
  assert.deepEqual(await response.json(), {
    ok: false,
    error: "Telegram rejected one or more messages",
    delivered: 1,
    failed: 1,
  });
});

test("webhook rejects an invalid Telegram secret", async () => {
  let fetchCalls = 0;
  const response = await withFetch(
    async () => {
      fetchCalls += 1;
      return json({ ok: true });
    },
    () => worker.fetch(webhookRequest("0568", { secret: "wrong" }), env)
  );

  assert.equal(response.status, 401);
  assert.equal(fetchCalls, 0);
});

test("webhook ignores non-private chats", async () => {
  let fetchCalls = 0;
  const response = await withFetch(
    async () => {
      fetchCalls += 1;
      return json({ ok: true });
    },
    () =>
      worker.fetch(
        webhookRequest("0568", {
          chatId: "-100123",
          chatType: "supergroup",
        }),
        env
      )
  );

  assert.deepEqual(await response.json(), { ok: true, ignored: true });
  assert.equal(fetchCalls, 0);
});

test("/id returns the sender's numeric Telegram ID", async () => {
  const calls = [];
  const response = await withFetch(
    async (url, options) => {
      calls.push({ url: String(url), options });
      return json({ ok: true });
    },
    () => worker.fetch(webhookRequest("/id", { fromId: "987654" }), env)
  );

  assert.equal(response.status, 200);
  assert.equal(calls.length, 1);
  assert.match(calls[0].url, /\/sendMessage$/);
  assert.match(requestPayload(calls[0]).text, /987654/);
});

test("permitted lookup forwards user ID and sends image with price", async () => {
  const calls = [];
  const response = await withFetch(
    async (url, options) => {
      const call = { url: String(url), options };
      calls.push(call);
      if (call.url.includes("/internal/telegram/product-lookup/")) {
        return json({
          ok: true,
          product: {
            code: "0568",
            name: "Test bouquet",
            price_display: "2,500,000 تومان",
            image_url: "https://www.zadconcept.ir/media/product.webp",
          },
        });
      }
      return json({ ok: true });
    },
    () => worker.fetch(webhookRequest("0568", { fromId: "101" }), env)
  );

  assert.equal(response.status, 200);
  assert.equal(calls.length, 2);
  assert.deepEqual(requestPayload(calls[0]), {
    code: "0568",
    telegram_user_id: "101",
  });
  assert.match(calls[1].url, /\/sendPhoto$/);
  assert.match(requestPayload(calls[1]).caption, /2,500,000 تومان/);
});

test("lookup permission denial is returned as a user-facing message", async () => {
  const calls = [];
  const response = await withFetch(
    async (url, options) => {
      const call = { url: String(url), options };
      calls.push(call);
      if (call.url.includes("/internal/telegram/product-lookup/")) {
        return json(
          { ok: false, error: "Telegram user is not allowed" },
          403
        );
      }
      return json({ ok: true });
    },
    () => worker.fetch(webhookRequest("0568"), env)
  );

  assert.equal(response.status, 200);
  assert.equal(calls.length, 2);
  assert.match(calls[1].url, /\/sendMessage$/);
  assert.match(requestPayload(calls[1]).text, /اجازه/);
});
