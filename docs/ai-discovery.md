# AI search discovery and measurement

The existing public sitemap, canonical URLs, crawlable HTML and truthful structured
data are the discovery sources. Search crawler access is independent from model
training crawler access; do not enable training access as an SEO requirement.

## IndexNow

`python manage.py submit_indexnow` notifies added, changed and removed public URLs.
New URLs are detected by comparing the sitemap with the last successful snapshot,
including URLs whose model timestamp predates that run. Removed URLs are notified
once; changed URLs must still be public. State advances only after every batch
succeeds, using a timestamp captured before URL collection. A failed batch keeps
the previous state so the next scheduled run can retry (duplicates are possible).

The production systemd unit runs from `/var/www/zad/app`. Use `--dry-run` for
inspection or `--all` for a deliberate full refresh. Keep the runtime key and state
outside source control. HTTP 200/202 acceptance does not guarantee indexing,
ranking or inclusion in an AI answer.

## Existing analytics events

The existing analytics script adds `ai_source` and the compatible `traffic_source`
parameter to page, product, lead and contact events. Allowed labels are `chatgpt`,
`perplexity`, `claude`, `gemini`, and `copilot`, based on recognized referrer hosts
or an allowlisted `utm_source`. Host matching uses domain boundaries.

Attribution survives internal navigation in the same tab for up to 30 minutes via
sessionStorage. Only the source label and timestamp are stored; referrer URLs,
prompts and query strings are not stored by this attribution feature. A new
non-AI campaign or external non-AI referrer clears attribution. Blocked storage
does not interrupt browsing or event delivery. Existing analytics configuration
and consent controls still apply.

This measures identifiable referral traffic, not all AI mentions or citations.
Apps that omit both referrer and campaign tags cannot be identified. To break down
events in GA4 reports, register `ai_source` as an event-scoped custom dimension in
the existing property; historical values are not backfilled. Verify collection in
GA4 before reporting production conversion counts.

## Verification

```text
python manage.py test main.tests.test_indexnow main.tests.test_seo
node --test main/tests/js/analytics.test.mjs
```

Bing AI Performance reports Microsoft Copilot and participating partners. Its
citation counts must not be described as ChatGPT traffic or guaranteed sales.
