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
                "url": filter_url,
                "filter_url": filter_url,
                "category_url": category_url(category),
                "is_active": (
                    selected_slug == category.slug
                    and (not include_section or selected_section == category.section)
                ),
            }
        )
    return links
