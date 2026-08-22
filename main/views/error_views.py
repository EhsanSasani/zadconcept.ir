from django.shortcuts import render


def custom_404(request, exception):
    """Render the site's branded not-found page with the shared base layout."""
    context = {
        "meta_title": "صفحه پیدا نشد | ZAD",
        "meta_description": "صفحه مورد نظر پیدا نشد.",
        "robots_content": "noindex,nofollow",
        "page_type": "error-404",
        "is_home": True,
    }
    return render(request, "main/errors/404.html", context, status=404)
