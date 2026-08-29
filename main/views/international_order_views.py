from django.conf import settings
from django.shortcuts import render
from django.urls import reverse

from ..page_context import _default_context
from ..site_content import INTERNATIONAL_FAQ_EN, INTERNATIONAL_FAQ_FA


def international_orders(request):
    fa_url = f"{settings.ZAD_SITE_URL}{reverse('international_orders')}"
    en_url = f"{settings.ZAD_SITE_URL}{reverse('international_orders_en')}"
    context = _default_context(
        request,
        page_type="policy",
        active_nav="",
        meta_title="سفارش گل از خارج ایران برای مشهد | زاد",
        meta_description="ثبت سفارش گل و هدیه از خارج ایران با پرداخت ارزی و تحویل محلی برای گیرنده در مشهد.",
        faq_items=INTERNATIONAL_FAQ_FA,
        include_faq_schema=True,
        alternate_links=[
            {"language": "fa", "url": fa_url},
            {"language": "en", "url": en_url},
            {"language": "x-default", "url": fa_url},
        ],
        content_page="international-orders",
        suppress_default_hero=True,
    )
    return render(request, "main/pages/international/orders_fa.html", context)


def international_orders_en(request):
    fa_url = f"{settings.ZAD_SITE_URL}{reverse('international_orders')}"
    en_url = f"{settings.ZAD_SITE_URL}{reverse('international_orders_en')}"
    context = _default_context(
        request,
        page_type="policy",
        active_nav="",
        meta_title="Send Flowers to Mashhad, Iran | ZAD",
        meta_description="Order flowers, gifts, and bakery items from abroad for local delivery to your recipient in Mashhad, Iran.",
        faq_items=INTERNATIONAL_FAQ_EN,
        include_faq_schema=True,
        language="en",
        html_lang="en",
        html_dir="ltr",
        og_locale="en_US",
        alternate_links=[
            {"language": "fa", "url": fa_url},
            {"language": "en", "url": en_url},
            {"language": "x-default", "url": fa_url},
        ],
        suppress_default_hero=True,
        content_page="international-orders",
    )
    return render(request, "main/pages/international/orders_en.html", context)
