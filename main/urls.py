from django.urls import path
from django.views.generic import RedirectView
from django.templatetags.static import static

from . import views
from .telegram_product_lookup import telegram_product_lookup
from .telegram_same_day.webhook import telegram_webhook
from . import studio_views

urlpatterns = [
    path("studio/", studio_views.dashboard, name="studio_dashboard"),
    path("studio/products/", studio_views.products, name="studio_products"),
    path("studio/products/add/", studio_views.product_add, name="studio_product_add"),
    path("studio/products/<int:pk>/edit/", studio_views.product_edit, name="studio_product_edit"),
    path("studio/products/<int:pk>/status/", studio_views.product_status, name="studio_product_status"),
    path("studio/florists/", studio_views.florists, name="studio_florists"),
    path("studio/florists/add/", studio_views.florist_add, name="studio_florist_add"),
    path("studio/florists/<int:pk>/edit/", studio_views.florist_edit, name="studio_florist_edit"),
    path("studio/florists/<int:pk>/", studio_views.florist_profile, name="studio_florist_profile"),
    path("studio/analytics/", studio_views.analytics, name="studio_analytics"),
    path("studio/settings/", studio_views.settings_view, name="studio_settings"),
    path("studio/issues/<int:pk>/resolve/", studio_views.resolve_issue, name="studio_resolve_issue"),
    path("api/telegram/webhook/", telegram_webhook, name="telegram_webhook"),
    path(
        "favicon.ico",
        RedirectView.as_view(url=static("main/img/favicon.svg"), permanent=True),
        name="favicon",
    ),

    # Home
    path("", views.index, name="index"),

    # Weddings
    path("weddings/", views.weddings, name="weddings"),
    path("weddings/<slug:collection_slug>/", views.wedding_collection, name="wedding_collection"),

    # Flowers
    path("flowers/", views.flowers, name="flowers"),
    path("flowers/all/", views.flowers_all, name="flowers_all"),
    path("flowers/same-day/", views.flowers_same_day, name="flowers_same_day"),
    path("flowers/occasion/<str:slug>/", views.flower_occasion, name="flower_occasion"),
    path("flowers/<str:category_slug>/<str:slug>/", views.flower_product_detail, name="flower_product_detail"),
    path("flowers/<str:subcategory_slug>/", views.flower_subcategory, name="flower_subcategory"),

    # Bakery
    path("bakery/", views.bakery, name="bakery"),
    path("bakery/all/", views.bakery_all, name="bakery_all"),
    path("bakery/<str:category_slug>/<str:slug>/", views.bakery_product_detail, name="bakery_product_detail"),
    path("bakery/<str:subcategory_slug>/", views.bakery_subcategory, name="bakery_subcategory"),

    # Gifts
    path("gifts/", views.gifts, name="gifts"),
    path("gifts/all/", views.gifts_all, name="gifts_all"),
    path("gifts/<str:category_slug>/<str:slug>/", views.gift_product_detail, name="gift_product_detail"),
    path("gifts/<str:subcategory_slug>/", views.gift_subcategory, name="gift_subcategory"),

    # Events
    path("workshops/", views.events, name="events"),
    path("workshops/<str:slug>/", views.event_detail, name="event_detail"),
    path("events/", RedirectView.as_view(pattern_name="events", permanent=True)),
    path("events/<str:slug>/", RedirectView.as_view(pattern_name="event_detail", permanent=True)),

    # Mashhad landing pages
    path("mashhad/", views.mashhad_hub, name="mashhad_hub"),
    path("mashhad/flower-order/", views.mashhad_flower_order, name="mashhad_flower_order"),
    path("mashhad/flower-delivery/", views.mashhad_flower_delivery, name="mashhad_flower_delivery"),

    # Static pages
    path("contact/", views.contact, name="contact"),
    path("faq/", views.faq, name="faq"),
    path("about/", views.about, name="about"),
    path("privacy/", views.policy_page, {"policy_slug": "privacy"}, name="privacy"),
    path("terms/", views.policy_page, {"policy_slug": "terms"}, name="terms"),
    path("delivery-policy/", views.policy_page, {"policy_slug": "delivery"}, name="delivery_policy"),
    path("refund-cancellation/", views.policy_page, {"policy_slug": "refund"}, name="refund_policy"),
    path("payment-methods/", views.policy_page, {"policy_slug": "payment"}, name="payment_methods"),
    path("service-area/", views.policy_page, {"policy_slug": "service-area"}, name="service_area"),
    path("international-orders/", views.international_orders, name="international_orders"),
    path("en/international-orders/", views.international_orders_en, name="international_orders_en"),

    # Blog
    path("blog/", views.blog, name="blog"),
    path("blog/<str:slug>/", views.blog_detail, name="blog_detail"),

    # Forms / utility
    path("lead-request/", views.submit_lead_request, name="lead_request"),
    path(
        "internal/telegram/product-lookup/",
        telegram_product_lookup,
        name="telegram_product_lookup",
    ),
    path("robots.txt", views.robots_txt, name="robots_txt"),
    path("hero-styles.css", views.hero_styles_css, name="hero_styles_css"),
    path("csp-report/", views.csp_report, name="csp_report"),
    path("<str:key>.txt", views.indexnow_key, name="indexnow_key"),

    # Product legacy/detail routes
    path("product/<int:pk>/<str:slug>/", views.product_detail, name="product_detail"),
    path("flower/<int:pk>/", views.flower_detail_redirect, name="flower_detail_redirect"),
    path("flower/<int:pk>/<str:slug>/", views.flower_detail, name="flower_detail"),

    # Occasions
    path("occasions/", views.occasions, name="occasions"),
    path("occasions/<str:slug>/", views.occasion_detail, name="occasion_detail"),

    # Legacy
    path(
        "visit/",
        RedirectView.as_view(pattern_name="contact", permanent=True),
    ),
    path(
        "Visit",
        RedirectView.as_view(pattern_name="contact", permanent=True),
    ),
]
