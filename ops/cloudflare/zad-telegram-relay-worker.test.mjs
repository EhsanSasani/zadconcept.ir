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

const sameDayEnv = {
  ...env,
  SAME_DAY_WEBHOOK_URL: "https://www.zadconcept.ir/api/telegram/webhook/",
  TELEGRAM_CHANNEL_ID: "-10012345",
  TELEGRAM_DISCUSSION_GROUP_ID: "-10054321",
};

function sameDayRequest(update, secret = "webhook-secret") {
  return new Request("https://relay.example/telegram-webhook", {
    method: "POST", headers: { "Content-Type": "application/json", "X-Telegram-Bot-Api-Secret-Token": secret },
    body: JSON.stringify(update),
  });
}

test("same-day channel and edited posts preserve update identity and secret", async () => {
  for (const kind of ["channel_post", "edited_channel_post", "message", "edited_message"]) {
    const update = { update_id: 10, [kind]: { message_id: 70, chat: {
      id: kind.includes("channel") ? -10012345 : -10054321,
      type: kind.includes("channel") ? "channel" : "supergroup",
    } } };
    await withFetch(async (url, options) => {
      assert.equal(url, sameDayEnv.SAME_DAY_WEBHOOK_URL);
      assert.equal(options.headers["X-Telegram-Bot-Api-Secret-Token"], "webhook-secret");
      assert.deepEqual(JSON.parse(options.body), update);
      return json({ ok: true });
    }, async () => {
      assert.equal((await worker.fetch(sameDayRequest(update), sameDayEnv)).status, 200);
    });
  }
});

test("same-day Django failure is not acknowledged to Telegram", async () => {
  await withFetch(async () => json({ ok: false }, 503), async () => {
    const update = { update_id: 10, channel_post: { chat: { id: -10012345 } } };
    assert.equal((await worker.fetch(sameDayRequest(update), sameDayEnv)).status, 503);
  });
});

test("custom group forwards to Django and replies with escaped validation feedback", async () => {
  const customEnv = { ...sameDayEnv, TELEGRAM_STUDIO_CUSTOM_GROUP_ID: "-10087654" };
  const update = { update_id: 91, message: { message_id: 73,
    chat: { id: -10087654, type: "supergroup" }, photo: [{ file_id: "sample" }] } };
  const calls = [];
  const response = await withFetch(async (url, options) => {
    calls.push({ url: String(url), options });
    if (String(url) === customEnv.SAME_DAY_WEBHOOK_URL) {
      assert.deepEqual(JSON.parse(options.body), update);
      return json({ ok: true, result: "rejected", feedback: "فاکتور <تکراری>", reply_to_message_id: 73 });
    }
    return json({ ok: true });
  }, () => worker.fetch(sameDayRequest(update), customEnv));
  assert.equal(response.status, 200);
  assert.equal(calls.length, 2);
  assert.match(calls[1].url, /\/sendMessage$/);
  assert.equal(requestPayload(calls[1]).reply_parameters.message_id, 73);
  assert.match(requestPayload(calls[1]).text, /&lt;تکراری&gt;/);
});

test("direct group works without a channel and preserves photo replies and edits", async () => {
  const groupEnv = { ...env, SAME_DAY_WEBHOOK_URL: sameDayEnv.SAME_DAY_WEBHOOK_URL,
    TELEGRAM_SAME_DAY_GROUP_ID: "-10077777" };
  for (const kind of ["message", "edited_message"]) {
    const update = { update_id: 42, [kind]: { message_id: 71,
      chat: { id: -10077777, type: "supergroup" }, text: "2/680 t",
      reply_to_message: { message_id: 70, photo: [{ file_id: "photo" }] } } };
    await withFetch(async (url, options) => {
      assert.equal(url, groupEnv.SAME_DAY_WEBHOOK_URL);
      assert.deepEqual(JSON.parse(options.body), update);
      return json({ ok: true });
    }, async () => {
      assert.equal((await worker.fetch(sameDayRequest(update), groupEnv)).status, 200);
    });
  }
});

test("same-day network failure remains retryable", async () => {
  await withFetch(async () => { throw new Error("private URL"); }, async () => {
    const update = { update_id: 10, channel_post: { chat: { id: -10012345 } } };
    const response = await worker.fetch(sameDayRequest(update), sameDayEnv);
    assert.equal(response.status, 503);
    assert.doesNotMatch(await response.text(), /private URL/);
  });
});

test("unknown group is never forwarded to Django", async () => {
  await withFetch(async () => assert.fail("unexpected request"), async () => {
    const update = { update_id: 10, message: { chat: { id: -999, type: "supergroup" } } };
    assert.equal((await worker.fetch(sameDayRequest(update), sameDayEnv)).status, 200);
  });
});

function fileRequest(payload, secret = "relay-secret") {
  return new Request("https://relay.example/same-day-file", {
    method: "POST", headers: { "Authorization": `Bearer ${secret}`, "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

test("same-day file relay rejects bad secret before network", async () => {
  await withFetch(async () => assert.fail("unexpected request"), async () => {
    assert.equal((await worker.fetch(fileRequest({ file_id: "file" }, "wrong"), env)).status, 401);
  });
});

test("same-day file relay downloads only Telegram getFile result", async () => {
  let count = 0;
  await withFetch(async (url, options) => {
    count++;
    if (count === 1) {
      assert.equal(url, "https://api.telegram.org/botbot-token/getFile");
      assert.deepEqual(JSON.parse(options.body), { file_id: "file" });
      return json({ ok: true, result: { file_path: "photos/file_1.jpg" } });
    }
    assert.equal(url, "https://api.telegram.org/file/botbot-token/photos/file_1.jpg");
    return new Response("image bytes");
  }, async () => {
    const response = await worker.fetch(fileRequest({ file_id: "file" }), env);
    assert.equal(response.status, 200);
    assert.equal(await response.text(), "image bytes");
    assert.equal(count, 2);
  });
});

test("file relay rejects malicious paths and oversize responses", async () => {
  for (const path of ["../x.jpg", "/x.jpg", "https://evil.example/x.jpg"]) {
    await withFetch(async () => json({ ok: true, result: { file_path: path } }), async () => {
      assert.equal((await worker.fetch(fileRequest({ file_id: "file" }), env)).status, 502);
    });
  }
  let count = 0;
  await withFetch(async () => {
    if (++count === 1) return json({ ok: true, result: { file_path: "photos/x.jpg" } });
    return new Response("x", { headers: { "Content-Length": "20000001" } });
  }, async () => {
    assert.equal((await worker.fetch(fileRequest({ file_id: "file" }), env)).status, 502);
  });
});
