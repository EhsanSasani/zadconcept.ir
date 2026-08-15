# ZAD Telegram integration v1

This document is the repository reference for the Telegram integration currently
deployed for ZAD. It intentionally documents variable names and operational
flows without storing credentials.

## Scope

Version 1 provides two flows:

1. New website lead forms are delivered to one authorized Telegram chat.
2. The authorized Telegram user can send a product code and receive the first
   product gallery image with its code and name.

Dynamic users, permissions, prices, stock, and reports are not part of v1.

## Architecture

```text
Website form
  -> Django / PostgreSQL
  -> Cloudflare Worker relay
  -> Telegram Bot API
  -> authorized chat

Authorized Telegram user
  -> Telegram webhook
  -> Cloudflare Worker
  -> protected Django product lookup endpoint
  -> PostgreSQL / public media URL
  -> Telegram Bot API
  -> product image
```

The Worker is used because direct outbound access from the production VPS to
Telegram was not reliable. The bot token stays in Cloudflare; Django only knows
the shared relay secret.

## Repository files

```text
.env.example
config/settings.py
main/telegram_notifications.py
main/test_telegram_lead_notifications.py
main/test_telegram_relay_hotfix.py
main/telegram_product_lookup.py
main/test_telegram_product_lookup.py
main/urls.py
ops/cloudflare/zad-telegram-relay-worker.js
```

## Runtime configuration

Production Django `.env`:

```env
TELEGRAM_LEAD_RELAY_URL=https://<worker-subdomain>.workers.dev/
TELEGRAM_LEAD_RELAY_SECRET=<shared-secret>
TELEGRAM_LEAD_TIMEOUT_SECONDS=5
```

`TELEGRAM_LEAD_BOT_TOKEN` and `TELEGRAM_LEAD_CHAT_ID` remain available as a
legacy direct-send fallback. Leave them empty when the Cloudflare relay is in
use; the recommended production configuration keeps the bot token only in
Cloudflare.

Cloudflare Worker variables and secrets:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
RELAY_SECRET
TELEGRAM_WEBHOOK_SECRET
```

`RELAY_SECRET` and `TELEGRAM_LEAD_RELAY_SECRET` must have the same value.
No real values belong in Git.

## Outbound lead flow

`send_lead_request_notification()` formats the saved `LeadRequest` and posts it
to the Worker with:

```text
Authorization: Bearer <shared-secret>
Content-Type: application/json; charset=utf-8
User-Agent: Mozilla/5.0 (compatible; ZAD-Backend/1.0; +https://www.zadconcept.ir/)
```

The User-Agent is required because Cloudflare Browser Integrity Check rejected
Python urllib's default signature with HTTP 403 / Cloudflare error 1010.

The Worker validates `RELAY_SECRET`, then calls Telegram `sendMessage` for
`TELEGRAM_CHAT_ID`.

## Inbound product lookup flow

Telegram posts message updates to:

```text
https://<worker-subdomain>.workers.dev/telegram-webhook
```

The Worker validates `X-Telegram-Bot-Api-Secret-Token` against
`TELEGRAM_WEBHOOK_SECRET`, and only accepts a private message whose sender and
chat IDs both equal `TELEGRAM_CHAT_ID`.

For a product code, the Worker calls:

```text
POST /internal/telegram/product-lookup/
Authorization: Bearer <shared-secret>
```

Django performs a case-insensitive lookup on `Product.product_code`, selects
the first image returned by the product's `gallery_images` relation, and
returns only:

```json
{
  "ok": true,
  "product": {
    "code": "0568",
    "name": "Product name",
    "image_url": "https://www.zadconcept.ir/media/.../product.webp"
  }
}
```

The endpoint does not expose arbitrary database access and does not write to
the database.

## Deployment sequence

1. Deploy the Django commit and set the relay URL and shared secret in the
   production `.env`.
2. Restart the Django service and run `python manage.py check`.
3. In Cloudflare Workers, replace the current Worker code with
   `ops/cloudflare/zad-telegram-relay-worker.js`.
4. Configure the four Worker variables/secrets listed above and deploy it.
5. Register the Telegram webhook using the deployed Worker URL and webhook
   secret.
6. Run both smoke tests: submit a website lead and send a known product code
   to the bot.

The Worker root accepts outbound lead relay requests. `/telegram-webhook`
accepts inbound Telegram updates. Do not expose either shared secret in source,
logs, screenshots, or documentation.

## Webhook registration

Use Telegram `setWebhook` with:

```text
url=https://<worker-subdomain>.workers.dev/telegram-webhook
secret_token=<TELEGRAM_WEBHOOK_SECRET>
allowed_updates=["message"]
```

The `secret_token` must contain only characters accepted by Telegram. A
64-character hexadecimal value is suitable.

## Verification

Local or production Django checks:

```bash
python manage.py check
python manage.py test \
  main.test_telegram_lead_notifications \
  main.test_telegram_relay_hotfix \
  main.test_telegram_product_lookup \
  --verbosity 1
git diff --check
```

Production smoke tests:

1. Confirm the `zad` systemd service is active.
2. Confirm `https://www.zadconcept.ir/` returns HTTP 200.
3. Submit a real test lead and confirm Telegram delivery.
4. Send a known product code to the bot and confirm the image response.

## Secret rotation

- Rotate `RELAY_SECRET` in Cloudflare and
  `TELEGRAM_LEAD_RELAY_SECRET` on the VPS together, then restart `zad`.
- Rotate `TELEGRAM_WEBHOOK_SECRET` in Cloudflare and register the webhook again.
- If the bot token is exposed, revoke it in BotFather and replace
  `TELEGRAM_BOT_TOKEN` in Cloudflare.

## Current limitations and next version

Version 1 has one authorized Telegram ID. The planned v2 moves access control
to Django Admin using Telegram users plus assignable capabilities such as:

```text
receive_leads
lookup_products
```

That change should be implemented on top of the tagged v1 baseline rather than
mixed into this consolidation patch.
