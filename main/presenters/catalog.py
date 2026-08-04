"""Small, serializable catalog presentation contracts."""


def category_filter_links(
    base_url,
    categories,
    selected_slug=None,
    *,
    selected_section=None,
    include_section=False,
    category_url,
):
    links = [{"label": "All", "url": base_url, "is_active": not selected_slug}]

    for category in categories:
        filter_url = f"{base_url}?category={category.slug}"
        if include_section:
            filter_url += f"&section={category.section}"
        links.append(
            {
                "label": category.name,
                "url": category_url(category),
                "filter_url": filter_url,
                "is_active": (
                    selected_slug == category.slug
                    and (not include_section or selected_section == category.section)
                ),
            }
        )
    return links


def featured_selection(queryset, limit=10):
    """Prefer featured records, then fill without duplicates."""

    featured = list(queryset.filter(featured=True)[:limit])
    if len(featured) >= limit:
        return featured

    excluded_ids = [item.pk for item in featured]
    fallback = list(queryset.exclude(pk__in=excluded_ids)[: limit - len(featured)])
    return featured + fallback
