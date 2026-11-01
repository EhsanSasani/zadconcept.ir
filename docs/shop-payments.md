# Shop order and payment operations

The independent `shop` catalog is the only catalog that the cart/order services accept. Existing general, wedding and same-day products stay outside online checkout. Customer sessions are required; staff roles cannot check out through customer authentication.

## Runtime and fulfillment

`SHOP_PAYMENT_ENABLED` defaults to false and `SHOP_PAYMENT_BACKEND` defaults to empty. With no real adapter, visitors can browse and retain a cart, but no order or stock reservation is created. No payment provider has been selected or integrated by this change. Never configure `main.tests.*` or a `test_only` adapter in production; the service rejects those adapters when `IS_PRODUCTION` is true.

Staff with `main.manage_shop` configure fulfillment in the shop panel. Pickup starts enabled. Mashhad delivery starts disabled with an unspecified fee. Delivery requires an explicit fee (including zero for intentional free delivery), a complete address and the fixed city Mashhad. The order snapshots item subtotal, shipping fee, final payable amount and recipient details. Subsequent configuration changes cannot change an existing order's charge.

Money in products, carts and orders is integer toman. The adapter receives rial, explicitly multiplied by ten. Server product prices and stock determine the order; submitted totals only express the amount the customer has reviewed and must match the recalculated amount.

## Adapter contract

Implement a server-side adapter class named by `SHOP_PAYMENT_BACKEND`. It must expose stable `name`, `merchant_id` and `allowed_hosts` (the exact HTTPS hosted payment domains). Credentials belong only in runtime environment configuration.

- `request_payment(order_id, amount_rial, callback_url, idempotency_key)` returns `main.shop_payments.GatewayRequest(authority, payment_url)`. Use the supplied durable attempt UUID as provider idempotency identity. Never put credentials in the returned URL.
- `verify_payment(authority, order_id, amount_rial)` performs the provider's authenticated server-to-server verification and returns `GatewayVerification(outcome, authority, order_id, amount_rial, reference, merchant_id)`.
- Verification identity, amount and merchant fields must come from trustworthy provider evidence. Do not echo browser callback fields as evidence. The selected provider's documented API must be inspected and implemented before enabling the adapter.
- `outcome` is `paid`, `rejected` or `pending`. Use `rejected` only for a definitive result that the payment did not succeed. Network errors, ambiguous outcomes and provider pending states must remain unresolved. A paid result requires the unique provider transaction reference.

The browser's success/cancellation flag is ignored as settlement proof. The service checks amount, order, authority, merchant and unique transaction reference. Verification leases prevent duplicate in-flight work. A verified payment after stock was released enters review and cannot fulfill automatically.

## Reservations and reconciliation

Creating an order reserves available units for 20 minutes using a transaction, row locks and conditional inventory updates. Every reservation/release increments inventory version; a stale management form cannot restore units that another request reserved. Manual stock changes require a reason and create an audit entry. The management quantity means currently available, unreserved units.

Schedule these commands after enabling a real provider:

```bash
python manage.py reconcile_shop_payments --limit 100
python manage.py expire_shop_orders --limit 100
python manage.py prune_customer_login_limits
```

Reconciliation verifies existing pending/review attempts that have an authority. It prints counts only. Expiry releases orders only when no requesting, pending or review attempt exists. Repeated cancellation/expiry cannot restock twice.

An uncertain request with no returned authority requires operator review using its durable attempt UUID and the chosen provider's reconciliation tools. It must not be automatically retried or released: the remote provider may have accepted the charge before the connection failed. Selecting a provider also requires defining how these attempts are reconciled safely. This generic boundary does not claim live provider verification, refunds or automatic fulfillment.

Framework references used for transaction/constraint design: [Django 6 transactions](https://docs.djangoproject.com/en/6.0/topics/db/transactions/), [querysets and locking](https://docs.djangoproject.com/en/6.0/ref/models/querysets/), [database constraints](https://docs.djangoproject.com/en/6.0/ref/models/constraints/). SQLite tests cover conditional/idempotent behavior; real database concurrency must be checked on the configured production database before payment activation.
