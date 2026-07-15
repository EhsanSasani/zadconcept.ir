import json

from django import template
from django.utils.safestring import mark_safe


register = template.Library()


@register.filter
def json_ld(graph):
    """Serialize JSON-LD while preventing user content from closing the script tag."""
    payload = json.dumps(
        {"@context": "https://schema.org", "@graph": graph or []},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    payload = (
        payload.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )
    return mark_safe(payload)
