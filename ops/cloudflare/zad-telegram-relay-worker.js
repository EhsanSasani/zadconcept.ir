const TELEGRAM_API_BASE = "https://api.telegram.org";
const PRODUCT_LOOKUP_URL =
  "https://www.zadconcept.ir/internal/telegram/product-lookup/";
const TELEGRAM_WEBHOOK_PATH = "/telegram-webhook";

function jsonResponse(payload, status = 200) {
  return Response.json(payload, { status });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function telegramRequest(env, method, payload) {
  const response = await fetch(
    `${TELEGRAM_API_BASE}/bot${env.TELEGRAM_BOT_TOKEN}/${method}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );

  let result;

  try {
    result = await response.json();
  } catch {
    result = {};
  }

  return {
    ok: response.ok && result.ok === true,
    status: response.status,
    result,
  };
}

async function sendText(env, chatId, text, replyToMessageId) {
  return telegramRequest(env, "sendMessage", {
    chat_id: chatId,
    text,
    parse_mode: "HTML",
    link_preview_options: { is_disabled: true },
    ...(replyToMessageId ? { reply_parameters: { message_id: replyToMessageId, allow_sending_without_reply: true } } : {}),
  });
}

function relayChatIds(payload) {
  if (
    !Object.prototype.hasOwnProperty.call(payload, "chat_ids") ||
    !Array.isArray(payload.chat_ids) ||
    !payload.chat_ids.length
  ) {
    return null;
  }

  const rawIds = payload.chat_ids;

  if (rawIds.length > 50) {
    return null;
  }

  const chatIds = [
    ...new Set(rawIds.map((value) => String(value ?? "").trim())),
  ];

  if (
    !chatIds.length ||
    chatIds.some((chatId) => !/^-?\d+$/.test(chatId))
  ) {
    return null;
  }

  return chatIds;
}

async function handleOutboundRelay(request, env) {
  const authorization = request.headers.get("Authorization");

  if (!env.RELAY_SECRET || authorization !== `Bearer ${env.RELAY_SECRET}`) {
    return jsonResponse({ ok: false, error: "Unauthorized" }, 401);
  }

  let payload;

  try {
    payload = await request.json();
  } catch {
    return jsonResponse({ ok: false, error: "Invalid JSON" }, 400);
  }

  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return jsonResponse({ ok: false, error: "Invalid JSON" }, 400);
  }

  const text = typeof payload.text === "string" ? payload.text.trim() : "";
  const chatIds = relayChatIds(payload);

  if (!text || text.length > 4096) {
    return jsonResponse({ ok: false, error: "Invalid message text" }, 400);
  }

  if (!chatIds) {
    return jsonResponse({ ok: false, error: "Invalid chat IDs" }, 400);
  }

  const deliveries = await Promise.allSettled(
    chatIds.map((chatId) => sendText(env, chatId, text))
  );
  const failed = deliveries.filter(
    (delivery) => delivery.status === "rejected" || !delivery.value.ok
  ).length;

  if (failed) {
    return jsonResponse(
      {
        ok: false,
        error: "Telegram rejected one or more messages",
        delivered: deliveries.length - failed,
        failed,
      },
      502
    );
  }

  return jsonResponse({ ok: true, delivered: deliveries.length });
}

async function lookupProduct(env, code, telegramUserId) {
  const response = await fetch(PRODUCT_LOOKUP_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.RELAY_SECRET}`,
      "Content-Type": "application/json; charset=utf-8",
      "User-Agent":
        "Mozilla/5.0 (compatible; ZAD-Telegram-Worker/1.0; +https://www.zadconcept.ir/)",
    },
    body: JSON.stringify({
      code,
      telegram_user_id: telegramUserId,
    }),
  });

  let result;

  try {
    result = await response.json();
  } catch {
    result = {};
  }

  return {
    ok: response.ok && result.ok === true,
    status: response.status,
    result,
  };
}

async function handleTelegramWebhook(request, env) {
  const webhookSecret = request.headers.get(
    "X-Telegram-Bot-Api-Secret-Token"
  );

  if (
    !env.TELEGRAM_WEBHOOK_SECRET ||
    webhookSecret !== env.TELEGRAM_WEBHOOK_SECRET
  ) {
    return jsonResponse({ ok: false, error: "Unauthorized webhook" }, 401);
  }

  let update;

  try {
    update = await request.json();
  } catch {
    return jsonResponse({ ok: false, error: "Invalid JSON" }, 400);
  }

  const sameDayMessage = update?.channel_post ?? update?.edited_channel_post ??
    update?.message ?? update?.edited_message;
  const sameDayChat = String(sameDayMessage?.chat?.id ?? "");
  if (env.SAME_DAY_WEBHOOK_URL && sameDayChat &&
      [String(env.TELEGRAM_CHANNEL_ID ?? ""), String(env.TELEGRAM_DISCUSSION_GROUP_ID ?? ""),
       String(env.TELEGRAM_SAME_DAY_GROUP_ID ?? ""),
       String(env.TELEGRAM_STUDIO_CUSTOM_GROUP_ID ?? "")].includes(sameDayChat)) {
    try {
      const target = new URL(env.SAME_DAY_WEBHOOK_URL);
      if (target.protocol !== "https:") return jsonResponse({ ok: false }, 503);
      const response = await fetch(target.toString(), {
        method: "POST", redirect: "error", signal: AbortSignal.timeout(25000),
        headers: {
          "Content-Type": "application/json",
          "X-Telegram-Bot-Api-Secret-Token": env.TELEGRAM_WEBHOOK_SECRET,
          "User-Agent": "Mozilla/5.0 (compatible; ZAD-Telegram-Worker/1.0; +https://www.zadconcept.ir/)",
        },
        body: JSON.stringify(update),
      });
      // Do not acknowledge a failed Django delivery: let Telegram retry it.
      if (response.ok && sameDayChat === String(env.TELEGRAM_STUDIO_CUSTOM_GROUP_ID ?? "")) {
        const result = await response.json().catch(() => ({}));
        if (typeof result.feedback === "string" && result.feedback) {
          try {
            await sendText(env, sameDayChat, `${result.result === "rejected" ? "❌ ثبت نشد: " : "✅ "}${escapeHtml(result.feedback)}`, result.reply_to_message_id);
          } catch {
            // Ledger delivery already succeeded; a feedback outage must not replay it.
          }
        }
      }
      return jsonResponse({ ok: response.ok }, response.ok ? 200 : response.status);
    } catch {
      return jsonResponse({ ok: false }, 503);
    }
  }

  const message = update?.message;
  const fromId = String(message?.from?.id ?? "");
  const chatId = String(message?.chat?.id ?? "");
  const chatType = String(message?.chat?.type ?? "");

  if (
    !message ||
    chatType !== "private" ||
    !fromId ||
    fromId !== chatId
  ) {
    return jsonResponse({ ok: true, ignored: true });
  }

  const text = typeof message.text === "string" ? message.text.trim() : "";

  if (text === "/id") {
    await sendText(
      env,
      chatId,
      `شناسه عددی تلگرام شما: <code>${escapeHtml(fromId)}</code>`
    );
    return jsonResponse({ ok: true });
  }

  if (text === "/start" || text === "/help") {
    await sendText(
      env,
      chatId,
      "کد محصول را ارسال کنید. برای دیدن شناسه عددی خودتان /id را بفرستید."
    );
    return jsonResponse({ ok: true });
  }

  if (!text || text.length > 40) {
    await sendText(env, chatId, "کد محصول معتبر نیست.");
    return jsonResponse({ ok: true });
  }

  const lookup = await lookupProduct(env, text, fromId);

  if (!lookup.ok) {
    if (lookup.status === 403) {
      await sendText(
        env,
        chatId,
        "شما اجازه دریافت اطلاعات محصول را ندارید."
      );
    } else if (lookup.status === 404) {
      const messageText =
        lookup.result?.error === "Product image not found"
          ? "برای این محصول تصویری ثبت نشده است."
          : "محصولی با این کد پیدا نشد.";
      await sendText(env, chatId, messageText);
    } else {
      await sendText(env, chatId, "خطا در دریافت اطلاعات محصول.");
    }

    return jsonResponse({ ok: true });
  }

  const product = lookup.result.product;
  const caption = [
    `<b>${escapeHtml(product.code)}</b>`,
    escapeHtml(product.name),
    `💰 ${escapeHtml(product.price_display)}`,
  ].join("\n");
  const telegram = await telegramRequest(env, "sendPhoto", {
    chat_id: chatId,
    photo: product.image_url,
    caption,
    parse_mode: "HTML",
  });

  if (!telegram.ok) {
    await sendText(
      env,
      chatId,
      `تصویر پیدا شد، اما تلگرام نتوانست آن را نمایش دهد.\n${escapeHtml(
        product.image_url
      )}`
    );
  }

  return jsonResponse({ ok: true });
}

// Narrow authenticated file relay; never accepts arbitrary URLs or API methods.
async function handleSameDayFile(request, env) {
  if (!env.RELAY_SECRET || request.headers.get("Authorization") !== `Bearer ${env.RELAY_SECRET}`) {
    return jsonResponse({ ok: false }, 401);
  }
  try {
    const payload = await request.json();
    if (!payload || typeof payload.file_id !== "string" || !/^[A-Za-z0-9_-]{1,512}$/.test(payload.file_id)) {
      return jsonResponse({ ok: false }, 400);
    }
    const file = await telegramRequest(env, "getFile", { file_id: payload.file_id });
    const path = file.result?.result?.file_path;
    if (!file.ok || typeof path !== "string" || !/^[A-Za-z0-9_/-]+\.[A-Za-z0-9]+$/.test(path) || path.startsWith("/") || path.includes("..")) {
      return jsonResponse({ ok: false }, 502);
    }
    const response = await fetch(`${TELEGRAM_API_BASE}/file/bot${env.TELEGRAM_BOT_TOKEN}/${path}`, {
      redirect: "error", signal: AbortSignal.timeout(15000),
    });
    if (!response.ok || Number(response.headers.get("Content-Length") || 0) > 20000000) {
      return jsonResponse({ ok: false }, 502);
    }
    const reader = response.body.getReader();
    const chunks = [];
    let length = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      length += value.length;
      if (length > 20000000) {
        await reader.cancel();
        return jsonResponse({ ok: false }, 502);
      }
      chunks.push(value);
    }
    return new Response(new Blob(chunks), {
      headers: { "Content-Type": "application/octet-stream", "Cache-Control": "no-store" },
    });
  } catch {
    return jsonResponse({ ok: false }, 502);
  }
}

// Studio delivery has a separate, deliberately narrow envelope. It never
// accepts a URL, file_id, bot token, arbitrary API method or arbitrary group.
const STUDIO_PHOTO_LIMIT = 10000000;
const STUDIO_REQUEST_LIMIT = Math.ceil(STUDIO_PHOTO_LIMIT / 3) * 4 + 8192;
const STUDIO_RESPONSE_LIMIT = 65536;
const STUDIO_METHOD_FIELDS = {
  sendPhoto: ["method", "chat_id", "caption", "photo_base64"],
  deleteMessage: ["method", "chat_id", "message_id"],
  editMessageCaption: ["method", "chat_id", "message_id", "caption"],
};

function studioFailure(error, status, { retryable = false, uncertain = false, retryAfter } = {}) {
  const payload = { ok: false, error, retryable: retryable && !uncertain, uncertain };
  if (Number.isFinite(retryAfter)) payload.retry_after = Math.min(Math.max(Math.floor(retryAfter), 1), 86400);
  return jsonResponse(payload, status);
}

async function boundedJson(body, limit) {
  const declared = Number(body.headers.get("Content-Length"));
  if (Number.isFinite(declared) && declared > limit) throw new Error("body_too_large");
  if (!body.body) throw new Error("invalid_body");
  const reader = body.body.getReader();
  const chunks = [];
  let length = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      length += value.byteLength;
      if (length > limit) {
        await reader.cancel();
        throw new Error("body_too_large");
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const data = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    data.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(data));
}

function studioPhoto(encoded) {
  if (typeof encoded !== "string" || !encoded.length || encoded.length % 4 !== 0 ||
      encoded.length > Math.ceil(STUDIO_PHOTO_LIMIT / 3) * 4 || /[^A-Za-z0-9+/=]/.test(encoded)) return null;
  const padding = encoded.indexOf("=");
  if (padding !== -1 && (padding < encoded.length - 2 || !/^={1,2}$/.test(encoded.slice(padding)))) return null;
  let binary;
  try { binary = atob(encoded); } catch { return null; }
  if (binary.length < 5 || binary.length > STUDIO_PHOTO_LIMIT ||
      binary.charCodeAt(0) !== 255 || binary.charCodeAt(1) !== 216 || binary.charCodeAt(2) !== 255 ||
      binary.charCodeAt(binary.length - 2) !== 255 || binary.charCodeAt(binary.length - 1) !== 217) return null;
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index++) bytes[index] = binary.charCodeAt(index);
  return bytes;
}

function studioApiFailure(result, status, method) {
  const code = Number.isInteger(result.error_code) ? result.error_code : status;
  const description = typeof result.description === "string" ? result.description.toLowerCase() : "";
  if (code === 429 || status === 429) {
    return studioFailure("rate_limited", 429, { retryable: true, retryAfter: Number(result.parameters?.retry_after) });
  }
  if (code === 401) return studioFailure("telegram_unauthorized", 502);
  if (code === 403) return studioFailure("telegram_forbidden", 403);
  if (code === 400) {
    if (description.includes("message to delete not found") || description.includes("message to edit not found")) {
      return method === "deleteMessage" ? jsonResponse({ ok: true, result: true }) : studioFailure("message_not_found", 400);
    }
    if (description.includes("message is not modified")) {
      return method === "editMessageCaption" ? jsonResponse({ ok: true, result: true }) : studioFailure("message_not_modified", 400);
    }
    if (description.includes("message can't be deleted") || description.includes("message cannot be deleted")) {
      return studioFailure("message_cannot_be_deleted", 400);
    }
    return studioFailure("telegram_bad_request", 400);
  }
  if (code >= 500 && code <= 599) return studioFailure("telegram_server_error", 502, { retryable: true });
  return studioFailure("telegram_bad_request", 400);
}

async function handleStudioDelivery(request, env) {
  if (!env.RELAY_SECRET || request.headers.get("Authorization") !== `Bearer ${env.RELAY_SECRET}`) {
    return studioFailure("relay_unauthorized", 401);
  }
  const group = String(env.TELEGRAM_SAME_DAY_GROUP_ID ?? "").trim();
  if (!/^-?[1-9][0-9]{0,19}$/.test(group) || !group.startsWith("-") ||
      typeof env.TELEGRAM_BOT_TOKEN !== "string" || !/^[A-Za-z0-9:_-]{1,256}$/.test(env.TELEGRAM_BOT_TOKEN)) {
    return studioFailure("configuration_error", 503);
  }
  if (!(request.headers.get("Content-Type") ?? "").toLowerCase().startsWith("application/json")) {
    return studioFailure("invalid_payload", 400);
  }
  let payload;
  try {
    payload = await boundedJson(request, STUDIO_REQUEST_LIMIT);
  } catch (error) {
    return studioFailure("invalid_payload", error?.message === "body_too_large" ? 413 : 400);
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload) ||
      typeof payload.method !== "string" ||
      !Object.prototype.hasOwnProperty.call(STUDIO_METHOD_FIELDS, payload.method)) {
    return studioFailure("invalid_payload", 400);
  }
  const fields = STUDIO_METHOD_FIELDS[payload.method];
  if (Object.keys(payload).length !== fields.length || Object.keys(payload).some((key) => !fields.includes(key)) ||
      !(typeof payload.chat_id === "string" || Number.isSafeInteger(payload.chat_id)) ||
      String(payload.chat_id) !== group ||
      (fields.includes("message_id") && (!Number.isSafeInteger(payload.message_id) || payload.message_id < 1)) ||
      (fields.includes("caption") && (typeof payload.caption !== "string" || !payload.caption.trim() || payload.caption.length > 1024))) {
    return studioFailure("invalid_payload", 400);
  }
  const sendingPhoto = payload.method === "sendPhoto";
  let body;
  const headers = {};
  if (sendingPhoto) {
    const photo = studioPhoto(payload.photo_base64);
    if (!photo) return studioFailure("invalid_payload", 400);
    body = new FormData();
    body.set("chat_id", group);
    body.set("caption", payload.caption);
    body.set("photo", new Blob([photo], { type: "image/jpeg" }), "product.jpg");
  } else {
    const { method, ...apiPayload } = payload;
    apiPayload.chat_id = group;
    body = JSON.stringify(apiPayload);
    headers["Content-Type"] = "application/json";
  }
  let response;
  try {
    response = await fetch(`${TELEGRAM_API_BASE}/bot${env.TELEGRAM_BOT_TOKEN}/${payload.method}`, {
      method: "POST", redirect: "error", signal: AbortSignal.timeout(25000), headers, body,
    });
  } catch {
    return studioFailure(sendingPhoto ? "transport_uncertain" : "transport_unavailable", 503, {
      uncertain: sendingPhoto, retryable: !sendingPhoto,
    });
  }
  let result;
  try {
    result = await boundedJson(response, STUDIO_RESPONSE_LIMIT);
  } catch {
    if (response.status === 429) {
      return studioFailure("rate_limited", 429, { retryable: true, retryAfter: Number(response.headers.get("Retry-After") ?? undefined) });
    }
    return studioFailure("invalid_response", 502, { uncertain: sendingPhoto, retryable: !sendingPhoto });
  }
  if (result && typeof result === "object" && result.ok === true && response.ok) {
    const value = result.result;
    const valid = sendingPhoto
      ? value && Number.isSafeInteger(value.message_id) && value.message_id > 0 && String(value.chat?.id) === group
      : payload.method === "deleteMessage" ? value === true : value === true || (value && typeof value === "object" && !Array.isArray(value));
    if (!valid) return studioFailure("invalid_response", 502, { uncertain: sendingPhoto, retryable: !sendingPhoto });
    return jsonResponse({ ok: true, result: value });
  }
  if (!result || typeof result !== "object" || result.ok !== false) {
    return studioFailure("invalid_response", 502, { uncertain: sendingPhoto, retryable: !sendingPhoto });
  }
  if (response.status !== 429 && (!Number.isInteger(result.error_code) || result.error_code < 400 || result.error_code > 599)) {
    return studioFailure("invalid_response", 502, { uncertain: sendingPhoto, retryable: !sendingPhoto });
  }
  return studioApiFailure(result, response.status, payload.method);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/studio-delivery") {
      return request.method === "POST" ? handleStudioDelivery(request, env) : studioFailure("invalid_payload", 405);
    }

    if (request.method === "GET") {
      return jsonResponse({ ok: true, service: "zad-telegram-relay" });
    }

    if (request.method !== "POST") {
      return jsonResponse({ ok: false, error: "Method not allowed" }, 405);
    }

    if (url.pathname === "/same-day-file") {
      return handleSameDayFile(request, env);
    }

    if (url.pathname === TELEGRAM_WEBHOOK_PATH) {
      return handleTelegramWebhook(request, env);
    }

    return handleOutboundRelay(request, env);
  },
};
