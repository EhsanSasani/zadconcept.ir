from django.core.paginator import Paginator


def pagination_context(request, page_obj):
    """Return a template-safe, query-preserving pagination contract."""

    query = request.GET.copy()
    query.pop("page", None)
    encoded_query = query.urlencode()

    page_links = []
    for value in page_obj.paginator.get_elided_page_range(
        page_obj.number,
        on_each_side=1,
        on_ends=1,
    ):
        if value == Paginator.ELLIPSIS:
            page_links.append({"is_ellipsis": True})
            continue
        page_links.append(
            {
                "number": value,
                "is_current": value == page_obj.number,
            }
        )

    return {
        "catalog_page_obj": page_obj,
        "pagination_links": page_links,
        "pagination_query_suffix": f"&{encoded_query}" if encoded_query else "",
    }
