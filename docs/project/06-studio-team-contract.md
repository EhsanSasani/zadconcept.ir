# Studio Team implementation contract

Approved on 2026-09-28. Incremental patch baseline: eac8108 (Studio UI v2).

## Product scope

- Persian RTL, existing warm ivory/sage/rose ZAD identity and local Estedad fonts.
- Independent branded login for manager dashboard and a separate mobile florist portal.
- Linked personal florist accounts, no Django Admin requirement for ordinary use.
- Florist creates a product with one photo, type, DAILY/CUSTOM, real factor code and price.
- Maker is a required selection from active florists with no default (approved update 2026-09-30).
- The authenticated submitter stays in created_by; production attribution follows the selected maker.
- Submitter can read their registrations for colleagues; unrelated peer records remain private.
- Valid DAILY uploads publish directly to SAME_DAY public catalog; no manager approval step.
- Telegram destination is existing TELEGRAM_SAME_DAY_GROUP_ID; send photo + price + factor only.
- Replies sold/withdrawn in this group preserve existing member permissions, update the central
  product, hide it from public available stock, and retire the bot's product message.
- Under 48 hours delete the Telegram product message; when permanent deletion is impossible,
  mark its caption sold/withdrawn and retain a visible delivery outcome. User accepted this fallback.
- Never delete ledger history or media for a sale/withdrawal.
- CUSTOM remains internal. No new outbound custom destination without explicit configuration/scope.
- Personal dashboard/products plus internal colleague profiles with name/photo/work gallery.
  Peer view excludes prices, sales values, invoice codes, private notes and mutation controls.
- Preserve original Telegram ingestion and private product lookup. Prevent outbound echo loops.
- No production deployment, live Telegram sends, native app, SMS provider, new JS framework or AI API.

## Ownership

- identity agent: main/studio_access.py, main/team_forms.py, main/team_views.py,
  main/team_urls.py, own tests, management command for account creation, studio accounts view/template.
- mobile UI agent: main/templates/main/team/, main/static/main/{css,js}/pages/team.*,
  team icons/manifest assets; coordinate template contract with identity agent.
- publishing agent: main/models.py, migration 0037, main/studio_publishing.py,
  main/studio_delivery.py, delivery management command, Telegram Django integration files, own tests.
- transport agent: main/studio_transport.py, Cloudflare Worker and its tests, transport tests,
  optional systemd worker units.
- root: main/urls.py include, config/settings.py, .env.example, existing studio_views/templates,
  integration, management reporting/queue visibility, browser QA, final docs and patch.

Do not edit another owner's files without coordination. Do not commit until root integrates.

## Shared schema (publishing agent owns changes)

- Florist.user: nullable OneToOne AUTH_USER_MODEL, SET_NULL, related_name='studio_florist'.
- Florist Meta permission ('manage_studio_accounts', 'مدیریت حساب‌های تیم استودیو').
- StudioProduct.Source.PORTAL = 'PORTAL'; submission_key nullable unique UUIDField.
- StudioDelivery durable outbox; FK record (related_name='deliveries'), action PUBLISH/RETIRE,
  status PENDING/SENDING/RETRY/SENT/UNCERTAIN/FAILED, attempts, next_attempt_at, locked_at,
  chat_id/message id and bounded diagnostic state. Publishing agent may refine ancillary fields.
  Publish jobs map to TelegramSameDayPost and StudioProduct Telegram identity fields on success.

## Service interface

main.studio_publishing.create_portal_record(*, user, florist, image, factor_code,
  product_type, production_type, price, submission_key, notes='') -> (record, created).
Forms normalize image through existing image_pipeline; service validates and stores ledger +
public DAILY projection + outbox atomically, no outbound network in the registration request.
Idempotency key is scoped to original actor; collisions must never reveal someone else's record.

main.studio_transport.send_photo(chat_id, photo_bytes, caption) -> Telegram Message dict.
main.studio_transport.delete_message(chat_id, message_id) -> bool.
main.studio_transport.edit_caption(chat_id, message_id, caption) -> Telegram result.
TelegramDeliveryError has safe code, retryable, uncertain and retry_after attributes.
Use TELEGRAM_SAME_DAY_RELAY_URL + '/studio-delivery' when configured, otherwise direct Bot API.
Worker /studio-delivery: authenticated JSON {method, chat_id, caption?, message_id?, photo_base64?}.
Only sendPhoto/deleteMessage/editMessageCaption; fixed Telegram host, no arbitrary URLs/methods.
Relay envelope {ok:true,result:...} or {ok:false,error:SAFE_CODE,retryable,uncertain,retry_after?}.
JPEG photo bytes <=10MB, request size bounded; no logs containing tokens or image payloads.

## Portal route/template contract

Route names: studio_login, studio_logout (POST), studio_accounts;
team_home, team_product_add, team_products, team_product_detail(pk), team_colleagues,
team_colleague_profile(pk), team_profile, team_manifest.
main/team_urls.py uses full paths ('team/...', 'studio/login/' etc), root includes at ''.
Templates main/team/{base,login,home,product_form,products,product_detail,colleagues,
colleague_profile,profile}.html. Identity agent and UI agent agree additional context directly.
Shared context: florist (current), active, can_manage_studio, request; own profile uses profile_form.
Product form: image, florist, product_type, production_type, factor_code, price, submission_key, notes.
POST supports HTML redirect and Accept: application/json: success {ok,record_id,redirect_url,
next_url,message,published,telegram_state}; validation 400 {ok:false,errors:{field:[messages]}}.
Use source-of-truth server errors and CSRF; never fake success on upload completion alone.

## UX acceptance

- Real mobile-first photo entry; camera/gallery, instant preview, clear replacement/removal.
- One primary action, required fields minimal, optional notes collapsed, Persian digit handling.
- Visible upload progress/status/cancel/retry; draft token preserved on failures; successful
  server acknowledgement clears draft. File draft persistence best-effort, explicitly report failures.
- Profile stays bound to session; maker is selected explicitly. Success page shows the selected maker
  with 'register next'. Personal production counts remain attributed to the maker.
- Tap targets >=44px, mobile inputs >=16px, keyboard/focus support, reduced motion, no page overflow.
- Local font/assets, progressive HTML fallback, installable Home Screen manifest; do not cache private
  authenticated pages in a service worker. Do not claim reliable background uploading on iOS.

## Gates

Read AGENTS.md. Meaningful tests for unauthorized access/ownership, idempotent submissions,
public DAILY versus private CUSTOM, retries/uncertainty, status mapping, message retirement,
48-hour fallback and preservation of existing Telegram flows. No live network in tests.
Run Django check, full test suite, makemigrations --check --dry-run, migrate --plan,
Worker tests and git diff --check. Root inspects browser 390/375/768/1440 and runs upload flow.
All production schema/config/worker schedule requirements must be in final rollout instructions.
