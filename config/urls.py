from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path

from main.sitemaps import sitemaps
from main.views.media_views import private_story_source

handler404 = "main.views.custom_404"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("media/stories/source/", private_story_source),
    path("media/stories/source/<path:filename>", private_story_source),
    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="sitemap"),
    path("", include("main.urls")),
]

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
