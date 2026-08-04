"""Lead submission policy independent from HTTP rendering."""

import hashlib

from django.conf import settings
from django.core.cache import cache


def is_rate_limited(remote_address):
    """Count a lead attempt without storing the caller's raw IP address."""

    digest = hashlib.sha256((remote_address or "unknown").encode("utf-8")).hexdigest()[:24]
    cache_key = f"lead-rate:{digest}"
    window = settings.LEAD_RATE_LIMIT_WINDOW
    limit = settings.LEAD_RATE_LIMIT_COUNT

    if cache.add(cache_key, 1, timeout=window):
        return False

    try:
        attempts = cache.incr(cache_key)
    except ValueError:
        cache.set(cache_key, 1, timeout=window)
        attempts = 1
    return attempts > limit


def save_lead(form, *, source_page=""):
    """Persist a validated lead while keeping source ownership explicit."""

    lead = form.save(commit=False)
    lead.source_page = source_page
    lead.save()
    return lead
