from django.http import Http404
from django.shortcuts import render

from .page_context import _default_context, _with_home
from .site_content import POLICY_PAGES


def _normalized_policy(policy):
    """Return template-safe policy data, including explicit empty item lists."""

    normalized_sections = []
    for section in policy.get("sections", []):
        paragraphs = section.get("paragraphs") or []
        items = section.get("items") or []
        if isinstance(paragraphs, str):
            paragraphs = [paragraphs]
        if isinstance(items, str):
            items = [items]
        normalized_sections.append(
            {
                "title": section.get("title", ""),
                "paragraphs": list(paragraphs),
                # The explicit key prevents Django templates from resolving the
                # missing value to dict.items(), which rendered raw tuples.
                "items": list(items),
            }
        )

    return {**policy, "sections": normalized_sections}


def policy_page(request, policy_slug):
    policy = POLICY_PAGES.get(policy_slug)
    if not policy:
        raise Http404("Policy page not found")

    breadcrumbs = _with_home([{"name": policy["title"], "url": None}])
    context = _default_context(
        request,
        page_type="policy",
        active_nav="",
        meta_title=policy["meta_title"],
        meta_description=policy["meta_description"],
        breadcrumbs=breadcrumbs,
        content_page="policy",
        suppress_default_hero=True,
    )
    context["policy"] = _normalized_policy(policy)
    return render(request, "policy_page.html", context)
