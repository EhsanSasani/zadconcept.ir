from django.urls import path

from . import team_views


urlpatterns = [
    path("studio/login/", team_views.studio_login, name="studio_login"),
    path("studio/logout/", team_views.studio_logout, name="studio_logout"),
    path("studio/accounts/", team_views.studio_accounts, name="studio_accounts"),
    path("team/", team_views.team_home, name="team_home"),
    path("team/products/", team_views.team_products, name="team_products"),
    path("team/products/add/", team_views.team_product_add, name="team_product_add"),
    path("team/products/<int:pk>/", team_views.team_product_detail, name="team_product_detail"),
    path("team/colleagues/", team_views.team_colleagues, name="team_colleagues"),
    path("team/colleagues/<int:pk>/", team_views.team_colleague_profile, name="team_colleague_profile"),
    path("team/profile/", team_views.team_profile, name="team_profile"),
    path("team/app.webmanifest", team_views.team_manifest, name="team_manifest"),
]
