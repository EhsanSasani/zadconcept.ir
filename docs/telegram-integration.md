# ZAD Telegram integration

This document is the repository reference for the Telegram integration
maintained for ZAD. It intentionally documents variable names and operational
flows without storing credentials. The immutable v1 baseline is tagged as
`telegram-integration-v1`; the current implementation is v2.

## Scope

Version 2 provides two permission-controlled flows:

1. New website lead forms are delivered to every active user with
   `can_receive_leads` enabled.
2. An active user with `can_lookup_products` can send a product code and
   receive its first gallery image (or cover-image fallback), code, name, and
   current display price.

Users and both permissions are managed in Django Admin. A user may have either
permission, both permissions, or neither permission.

## Architecture

```text
Website form
  -> Django / PostgreSQL
  -> active Telegram users with lead permission
  -> Cloudflare Worker relay
  -> Telegram Bot API
  -> authorized private chats

Telegram user
  -> Telegram webhook
  -> Cloudflare Worker
  -> protected Django product lookup endpoint
  -> active-user and lookup-permission check
  -> PostgreSQL / public media URL
  -> Telegram Bot API
  -> product image and price
```

The Worker is used because direct outbound access from the production VPS to
Telegram was not reliable. The bot token stays in Cloudflare; Django only knows
the shared relay secret.

## Repository files

```text
.env.example
config/settings.py
main/models.py
main/admin.py
main/migrations/0024_telegram_bot_user.py
main/telegram_notifications.py
main/test_telegram_lead_notifications.py
main/test_telegram_relay_hotfix.py
main/telegram_product_lookup.py
main/test_telegram_product_lookup.py
main/urls.py
ops/cloudflare/zad-telegram-relay-worker.js
ops/cloudflare/zad-telegram-relay-worker.test.mjs
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
RELAY_SECRET
TELEGRAM_WEBHOOK_SECRET
```

`RELAY_SECRET` and `TELEGRAM_LEAD_RELAY_SECRET` must have the same value.
The old `TELEGRAM_CHAT_ID` value may remain in Cloudflare for rollback to v1,
but v2 does not use it for routing or authorization. No real values belong in
Git.

## Admin access control

Open **کاربران ربات تلگرام** in Django Admin and create one row per person.
The numeric `telegram_user_id` is the private-chat identifier used for both
authorization and delivery. Ask the person to send `/id` to the bot and copy
the returned number into Admin. The username is optional and informational.

The two independent checkboxes map to these behaviors:

| Permission | Result |
| --- | --- |
| `can_receive_leads` | Receives new website form messages |
| `can_lookup_products` | Can request product image and price |

Turning off `is_active` disables all bot access immediately without deleting
the user.

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

Django adds the permitted recipients as a `chat_ids` array and makes one relay
request. The Worker validates `RELAY_SECRET`, removes duplicate IDs, and sends
the message to all recipients concurrently. If Django has no active user with
lead permission, it does not call the Worker and logs a warning; the submitted
lead remains saved in the database.

## Inbound product lookup flow

Telegram posts message updates to:

```text
https://<worker-subdomain>.workers.dev/telegram-webhook
```

The Worker validates `X-Telegram-Bot-Api-Secret-Token` against
`TELEGRAM_WEBHOOK_SECRET`, accepts only private messages whose sender and chat
IDs match, and forwards the sender's numeric ID to Django.

For a product code, the Worker calls:

```text
POST /internal/telegram/product-lookup/
Authorization: Bearer <shared-secret>

{"code": "0568", "telegram_user_id": "123456789"}
```

Django first requires an active `TelegramBotUser` with product lookup enabled.
It then performs a case-insensitive lookup on `Product.product_code`, selects
the first valid image returned by the product's `gallery_images` relation (or
the product cover image when the gallery is empty), and returns:

```json
{
  "ok": true,
  "product": {
    "code": "0568",
    "name": "Product name",
    "price_display": "2,500,000 تومان",
    "image_url": "https://www.zadconcept.ir/media/.../product.webp"
  }
}
```

The endpoint does not expose arbitrary database access and does not write to
the database. A missing, inactive, unknown, or unauthorized Telegram user ID
is rejected; possession of the relay secret alone does not grant user access.

## Deployment sequence

1. Deploy the Django v2 commit without changing the Worker.
2. Run `migrate`, `check`, the Telegram tests, and restart Django. Product
   lookup is intentionally unavailable until step 4 because the v1 Worker does
   not send a Telegram user ID.
3. In Django Admin, create the current Telegram admin and enable both
   permissions. Lead delivery continues through the v1 Worker's existing chat
   during this transition.
4. Replace the current Cloudflare code with
   `ops/cloudflare/zad-telegram-relay-worker.js` and deploy it.
5. Confirm the existing webhook is still registered, then test one known
   product code and one real website lead.
6. Add the remaining team members in Django Admin and assign only the access
   each person needs.

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
node --test ops/cloudflare/zad-telegram-relay-worker.test.mjs
git diff --check
```

Production smoke tests:

1. Confirm the `zad` systemd service is active.
2. Confirm `https://www.zadconcept.ir/` returns HTTP 200.
3. Submit a real test lead and confirm Telegram delivery.
4. Send a known product code as a permitted user and confirm image and price.
5. Confirm a user without lookup permission receives an access-denied message.
6. Submit a lead with two permitted recipients and confirm both receive it.

## Secret rotation

- Rotate `RELAY_SECRET` in Cloudflare and
  `TELEGRAM_LEAD_RELAY_SECRET` on the VPS together, then restart `zad`.
- Rotate `TELEGRAM_WEBHOOK_SECRET` in Cloudflare and register the webhook again.
- If the bot token is exposed, revoke it in BotFather and replace
  `TELEGRAM_BOT_TOKEN` in Cloudflare.

## Current limitations

Version 2 intentionally supports private chats only. Users are added manually
in Django Admin; there is no self-registration, audit log, stock reporting, or
command menu. A future capability should be added as another explicit boolean
permission with a migration, keeping authorization visible and easy to edit.
