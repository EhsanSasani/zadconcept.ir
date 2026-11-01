from django.urls import path
from . import shop_views as views

urlpatterns = [
    path("shop/", views.shop_home, name="shop_home"),
    path("shop/cart/", views.cart, name="shop_cart"),
    path("shop/cart/update/", views.cart_update, name="shop_cart_update"),
    path("shop/checkout/", views.checkout, name="shop_checkout"),
    path("shop/payment/verify/", views.payment_callback, name="shop_payment_callback"),
    path("shop/orders/<uuid:order_id>/", views.order_detail, name="shop_order_detail"),
    path("shop/orders/<uuid:order_id>/cancel/", views.order_cancel, name="shop_order_cancel"),
    path("shop/products/<str:slug>/", views.product_detail, name="shop_product_detail"),
    path("panel/shop/", views.shop_manage, name="shop_manage"),
    path("panel/shop/products/add/", views.shop_manage_product, name="shop_manage_product_add"),
    path("panel/shop/products/<int:pk>/", views.shop_manage_product, name="shop_manage_product"),
    path("panel/shop/orders/", views.shop_manage_orders, name="shop_manage_orders"),
    path("panel/shop/settings/", views.shop_manage_settings, name="shop_manage_settings"),
]
