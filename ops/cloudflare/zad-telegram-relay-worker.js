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

async function sendText(env, chatId, text) {
  return telegramRequest(env, "sendMessage", {
    chat_id: chatId,
    text,
    parse_mode: "HTML",
    link_preview_options: { is_disabled: true },
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

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === "GET") {
      return jsonResponse({ ok: true, service: "zad-telegram-relay" });
    }

    if (request.method !== "POST") {
      return jsonResponse({ ok: false, error: "Method not allowed" }, 405);
    }

    if (url.pathname === TELEGRAM_WEBHOOK_PATH) {
      return handleTelegramWebhook(request, env);
    }

    return handleOutboundRelay(request, env);
  },
};
