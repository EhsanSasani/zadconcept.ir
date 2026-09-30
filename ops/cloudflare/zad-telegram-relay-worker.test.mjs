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

const studioEnv = { ...env, TELEGRAM_SAME_DAY_GROUP_ID: "-10077777" };
const studioPhoto = Buffer.from([255, 216, 255, 224, 80, 72, 79, 84, 79, 255, 217]);
const studioPayload = { method: "sendPhoto", chat_id: "-10077777", caption: "قیمت: ۲۵۰٬۰۰۰ تومان\nفاکتور: A23",
  photo_base64: studioPhoto.toString("base64") };
const studioMessage = { message_id: 42, chat: { id: -10077777, type: "supergroup" } };

function studioRequest(payload = studioPayload, headers = {}) {
  return new Request("https://relay.example/studio-delivery", {
    method: "POST", headers: { Authorization: "Bearer relay-secret", "Content-Type": "application/json", ...headers },
    body: JSON.stringify(payload),
  });
}

test("studio rejects secret and destination before any Telegram call", async () => {
  await withFetch(async () => assert.fail("unexpected network call"), async () => {
    const unauthorized = await worker.fetch(studioRequest(studioPayload, { Authorization: "Bearer wrong" }), studioEnv);
    assert.equal(unauthorized.status, 401);
    assert.deepEqual(await unauthorized.json(), { ok: false, error: "relay_unauthorized", retryable: false, uncertain: false });
    assert.equal((await worker.fetch(studioRequest({ ...studioPayload, chat_id: "-999" }), studioEnv)).status, 400);
    assert.equal((await worker.fetch(studioRequest(), env)).status, 503);
    assert.equal((await worker.fetch(studioRequest(), { ...studioEnv, TELEGRAM_BOT_TOKEN: "" })).status, 503);
  });
});

test("studio only permits exact photo/delete/caption envelopes", async () => {
  const invalid = [
    null, [], { ...studioPayload, method: "sendMessage" }, { ...studioPayload, method: "toString" },
    { ...studioPayload, method: ["sendPhoto"] }, { ...studioPayload, chat_id: ["-10077777"] },
    { ...studioPayload, url: "https://attacker.example" }, { ...studioPayload, photo: "https://attacker.example/photo" },
    { ...studioPayload, caption: "" }, { ...studioPayload, caption: "🌹".repeat(513) },
    { method: "deleteMessage", chat_id: "-10077777", message_id: true },
    { method: "deleteMessage", chat_id: "-10077777", message_id: 0 },
    { method: "editMessageCaption", chat_id: "-10077777", message_id: 42 },
  ];
  await withFetch(async () => assert.fail("unexpected network call"), async () => {
    for (const payload of invalid) {
      assert.equal((await worker.fetch(studioRequest(payload), studioEnv)).status, 400);
    }
    assert.equal((await worker.fetch(studioRequest(studioPayload, { "Content-Type": "text/plain" }), studioEnv)).status, 400);
    assert.equal((await worker.fetch(new Request("https://relay.example/studio-delivery"), studioEnv)).status, 405);
  });
});

test("studio JPEG validation and declared/streamed request limits block network", async () => {
  await withFetch(async () => assert.fail("unexpected network call"), async () => {
    for (const encoded of ["https://example/image.jpg", "not-base64", "====", "aGVsbG8=", "", "AAAA=AAA"]) {
      assert.equal((await worker.fetch(studioRequest({ ...studioPayload, photo_base64: encoded }), studioEnv)).status, 400);
    }
    assert.equal((await worker.fetch(studioRequest(studioPayload, { "Content-Length": "14000000" }), studioEnv)).status, 413);
    const streamed = new Request("https://relay.example/studio-delivery", {
      method: "POST", headers: { Authorization: "Bearer relay-secret", "Content-Type": "application/json" },
      body: " ".repeat(13341529),
    });
    assert.equal((await worker.fetch(streamed, studioEnv)).status, 413);
    const oversize = Buffer.alloc(10000001);
    oversize[0] = 255; oversize[1] = 216; oversize[2] = 255;
    oversize[oversize.length - 2] = 255; oversize[oversize.length - 1] = 217;
    assert.equal((await worker.fetch(studioRequest({ ...studioPayload, photo_base64: oversize.toString("base64") }), studioEnv)).status, 400);
  });
});

test("studio photo becomes a bounded multipart upload to Telegram fixed host", async () => {
  await withFetch(async (url, options) => {
    assert.equal(url, "https://api.telegram.org/botbot-token/sendPhoto");
    assert.equal(options.redirect, "manual");
    assert.equal(options.method, "POST");
    assert.ok(options.signal);
    assert.ok(options.body instanceof FormData);
    assert.equal(options.body.get("chat_id"), "-10077777");
    assert.equal(options.body.get("caption"), studioPayload.caption);
    const photo = options.body.get("photo");
    assert.equal(photo.type, "image/jpeg");
    assert.equal(photo.name, "product.jpg");
    assert.deepEqual(Buffer.from(await photo.arrayBuffer()), studioPhoto);
    assert.equal(options.body.has("parse_mode"), false);
    return json({ ok: true, result: studioMessage });
  }, async () => {
    const response = await worker.fetch(studioRequest(), studioEnv);
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), { ok: true, result: studioMessage });
  });
});

test("studio getChat checks only configured group and omits private invite links", async () => {
  const payload = { method: "getChat", chat_id: "-10077777" };
  await withFetch(async (url, options) => {
    assert.equal(url, "https://api.telegram.org/botbot-token/getChat");
    assert.equal(options.method, "POST");
    assert.equal(options.redirect, "manual");
    assert.deepEqual(JSON.parse(options.body), { chat_id: "-10077777" });
    return json({ ok: true, result: { id: -10077777, type: "supergroup", title: "Ready",
      invite_link: "https://t.me/+PRIVATE", description: "PRIVATE DESCRIPTION" } });
  }, async () => {
    assert.deepEqual(await (await worker.fetch(studioRequest(payload), studioEnv)).json(), {
      ok: true, result: { id: -10077777, type: "supergroup", title: "Ready" },
    });
  });
});

test("studio getChat rejects unauthorized, foreign or expanded requests before network", async () => {
  const payload = { method: "getChat", chat_id: "-10077777" };
  await withFetch(async () => assert.fail("Unexpected Telegram call"), async () => {
    assert.equal((await worker.fetch(studioRequest(payload, { Authorization: "Bearer wrong" }), studioEnv)).status, 401);
    for (const invalid of [{ ...payload, chat_id: "-999" }, { ...payload, url: "https://attacker.example" },
      { ...payload, user_id: 123 }, { ...payload, photo_base64: studioPayload.photo_base64 }]) {
      assert.equal((await worker.fetch(studioRequest(invalid), studioEnv)).status, 400);
    }
  });
});

test("studio getChat rejects mismatched or nongroup Telegram identities", async () => {
  const payload = { method: "getChat", chat_id: "-10077777" };
  for (const result of [true, { id: -999, type: "group" }, { id: -10077777, type: "private" }]) {
    await withFetch(async () => json({ ok: true, result }), async () => {
      const response = await worker.fetch(studioRequest(payload), studioEnv);
      assert.equal(response.status, 502);
      assert.equal((await response.json()).uncertain, false);
    });
  }
});

test("studio getChat reports network failure without ambiguous send or credentials", async () => {
  await withFetch(async () => { throw new Error("bot-token relay-secret"); }, async () => {
    const response = await worker.fetch(studioRequest({ method: "getChat", chat_id: "-10077777" }), studioEnv);
    assert.equal(response.status, 503);
    const result = await response.json();
    assert.equal(result.error, "transport_unavailable");
    assert.equal(result.uncertain, false);
    assert.equal(result.retryable, true);
    assert.equal(result.diagnostic.kind, "network_failure");
    assert.equal(result.diagnostic.exception, "Error");
    assert.ok(result.diagnostic.elapsed_ms >= 0);
    assert.doesNotMatch(JSON.stringify(result), /bot-token|relay-secret/);
  });
});

test("studio delete and edit use only matching group message identity", async () => {
  for (const method of ["deleteMessage", "editMessageCaption"]) {
    const payload = { method, chat_id: "-10077777", message_id: 42, ...(method === "editMessageCaption" ? { caption: "فروخته شد" } : {}) };
    await withFetch(async (url, options) => {
      assert.equal(url, `https://api.telegram.org/botbot-token/${method}`);
      const { method: _method, ...expected } = payload;
      assert.deepEqual(JSON.parse(options.body), expected);
      return json({ ok: true, result: true });
    }, async () => {
      assert.deepEqual(await (await worker.fetch(studioRequest(payload), studioEnv)).json(), { ok: true, result: true });
    });
  }
});

test("studio 429 exposes safe retry delay without private Telegram diagnostics", async () => {
  await withFetch(async () => json({ ok: false, error_code: 429, description: "bot-token relay-secret",
    parameters: { retry_after: 43 } }, 429), async () => {
    const response = await worker.fetch(studioRequest(), studioEnv);
    assert.equal(response.status, 429);
    assert.deepEqual(await response.json(), { ok: false, error: "rate_limited", retryable: true, uncertain: false, retry_after: 43 });
  });
});

test("studio permanent and explicit transient Telegram errors retain distinct outcomes", async () => {
  for (const [code, error, retryable] of [[401, "telegram_unauthorized", false], [403, "telegram_forbidden", false],
    [400, "telegram_bad_request", false], [500, "telegram_server_error", true]]) {
    await withFetch(async () => json({ ok: false, error_code: code, description: "private-token" }, code), async () => {
      const response = await worker.fetch(studioRequest(), studioEnv);
      assert.deepEqual(await response.json(), { ok: false, error, retryable, uncertain: false });
    });
  }
});

test("studio lost photo response is uncertain but retirement transport can retry", async () => {
  await withFetch(async () => { throw new Error("https://api.telegram.org/botprivate-token/sendPhoto"); }, async () => {
    const send = await worker.fetch(studioRequest(), studioEnv);
    assert.deepEqual(await send.json(), { ok: false, error: "transport_uncertain", retryable: false, uncertain: true });
    const retire = await worker.fetch(studioRequest({ method: "deleteMessage", chat_id: "-10077777", message_id: 42 }), studioEnv);
    assert.deepEqual(await retire.json(), { ok: false, error: "transport_unavailable", retryable: true, uncertain: false });
  });
});

test("studio incomplete, malformed or oversized responses cannot trigger a duplicate send", async () => {
  const responses = [() => new Response("not JSON"), () => json({ ok: true, result: true }),
    () => json({ ok: false }), () => json({ ok: false, error_code: "500" }),
    () => json({ ok: false, error_code: true }), () => json({ ok: false, error_code: 200 }),
    () => json({ ok: true, result: { ...studioMessage, chat: { id: -999 } } }),
    () => new Response(" ".repeat(65537)), () => json({ ok: true, result: studioMessage }, 503)];
  for (const response of responses) {
    await withFetch(async () => response(), async () => {
      const result = await (await worker.fetch(studioRequest(), studioEnv)).json();
      assert.deepEqual(result, { ok: false, error: "invalid_response", retryable: false, uncertain: true });
    });
  }
});

test("studio deletion replay and same caption replay are idempotent", async () => {
  for (const [method, description] of [["deleteMessage", "Bad Request: message to delete not found"],
    ["editMessageCaption", "Bad Request: message is not modified"]]) {
    await withFetch(async () => json({ ok: false, error_code: 400, description }, 400), async () => {
      const payload = { method, chat_id: "-10077777", message_id: 42, ...(method === "editMessageCaption" ? { caption: "فروخته شد" } : {}) };
      assert.deepEqual(await (await worker.fetch(studioRequest(payload), studioEnv)).json(), { ok: true, result: true });
    });
  }
});

test("studio undeletable older message signals permanent caption fallback", async () => {
  await withFetch(async () => json({ ok: false, error_code: 400, description: "Bad Request: message can't be deleted" }, 400), async () => {
    const response = await worker.fetch(studioRequest({ method: "deleteMessage", chat_id: "-10077777", message_id: 42 }), studioEnv);
    assert.deepEqual(await response.json(), { ok: false, error: "message_cannot_be_deleted", retryable: false, uncertain: false });
  });
});

test("studio remains compatible when AbortSignal.timeout is unavailable", async () => {
  const descriptor = Object.getOwnPropertyDescriptor(AbortSignal, "timeout");
  Object.defineProperty(AbortSignal, "timeout", { configurable: true, value: undefined });
  try {
    await withFetch(async (url, options) => {
      assert.equal(options.redirect, "manual");
      assert.ok(options.signal instanceof AbortSignal);
      return json({ ok: true, result: { id: -10077777, type: "group", title: "Ready" } });
    }, async () => {
      const response = await worker.fetch(studioRequest({ method: "getChat", chat_id: "-10077777" }), studioEnv);
      assert.equal(response.status, 200);
    });
  } finally {
    Object.defineProperty(AbortSignal, "timeout", descriptor);
  }
});

test("studio deadline aborts a stalled request and reports a safe timeout", async () => {
  const originalTimeout = globalThis.setTimeout;
  globalThis.setTimeout = (callback, ms, ...args) => originalTimeout(callback, ms === 25000 ? 2 : ms, ...args);
  try {
    await withFetch(async (_url, options) => new Promise((_resolve, reject) => {
      options.signal.addEventListener("abort", () => reject(new DOMException("bot-token relay-secret", "AbortError")), { once: true });
    }), async () => {
      const response = await worker.fetch(studioRequest({ method: "getChat", chat_id: "-10077777" }), studioEnv);
      assert.equal(response.status, 503);
      const result = await response.json();
      assert.equal(result.diagnostic.kind, "timeout");
      assert.equal(result.uncertain, false);
      assert.doesNotMatch(JSON.stringify(result), /bot-token|relay-secret/);
    });
  } finally {
    globalThis.setTimeout = originalTimeout;
  }
});

test("studio deadline remains active while the response body is stalled", async () => {
  const originalTimeout = globalThis.setTimeout;
  globalThis.setTimeout = (callback, ms, ...args) => originalTimeout(callback, ms === 25000 ? 2 : ms, ...args);
  try {
    await withFetch(async (_url, options) => new Response(new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('{"ok":'));
        options.signal.addEventListener("abort", () => controller.error(new DOMException("Stopped", "AbortError")), { once: true });
      },
    })), async () => {
      const response = await worker.fetch(studioRequest({ method: "getChat", chat_id: "-10077777" }), studioEnv);
      assert.equal(response.status, 502);
      assert.equal((await response.json()).uncertain, false);
    });
  } finally {
    globalThis.setTimeout = originalTimeout;
  }
});


test("studio sends custom photo only to the configured custom group", async () => {
  const customEnv = { ...studioEnv, TELEGRAM_STUDIO_CUSTOM_GROUP_ID: "-5182713369" };
  const payload = { ...studioPayload, chat_id: "-5182713369" };
  await withFetch(async (url, options) => {
    assert.equal(options.body.get("chat_id"), "-5182713369");
    assert.equal(options.body.get("caption"), payload.caption);
    return json({ ok: true, result: { ...studioMessage, chat: { id: -5182713369, type: "group" } } });
  }, async () => {
    const response = await worker.fetch(studioRequest(payload), customEnv);
    assert.equal(response.status, 200);
    assert.equal((await response.json()).result.chat.id, -5182713369);
  });
  await withFetch(async () => assert.fail("unexpected network call"), async () => {
    assert.equal((await worker.fetch(studioRequest(payload), studioEnv)).status, 400);
    assert.equal((await worker.fetch(studioRequest({ ...payload, chat_id: "-999" }), customEnv)).status, 400);
  });
});

test("studio permits custom getChat and retirement without a daily destination", async () => {
  const customEnv = { ...studioEnv, TELEGRAM_SAME_DAY_GROUP_ID: "", TELEGRAM_STUDIO_CUSTOM_GROUP_ID: "-5182713369" };
  for (const payload of [
    { method: "getChat", chat_id: "-5182713369" },
    { method: "deleteMessage", chat_id: "-5182713369", message_id: 42 },
    { method: "editMessageCaption", chat_id: "-5182713369", message_id: 42, caption: "فروخته شد" },
  ]) {
    await withFetch(async (url, options) => {
      assert.equal(JSON.parse(options.body).chat_id, "-5182713369");
      return json({ ok: true, result: payload.method === "getChat" ? { id: -5182713369, type: "group" } : true });
    }, async () => {
      assert.equal((await worker.fetch(studioRequest(payload), customEnv)).status, 200);
    });
  }
});
