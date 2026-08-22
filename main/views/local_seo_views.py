from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from django.urls import reverse

from ..category_presentation import _category_card
from ..catalog_selectors import (
    _active_categories_for_section,
    _active_occasion_tags,
    _published_products_for_section,
)
from ..forms import LeadRequestForm
from ..managed_heroes import _get_site_hero
from ..models import Category
from ..page_context import _default_context, _with_home
from ..page_presentation import _hero_from_key


def mashhad_hub(request):
    curated_items = list(
        _published_products_for_section(Category.Section.FLOWERS).order_by(
            "-featured",
            "sort_order",
            "-created_at",
        )[:6]
    )

    breadcrumbs = _with_home([{"name": "Mashhad Orders", "url": None}])
    db_hero = _get_site_hero("mashhad")

    context = _default_context(
        request,
        page_type="local",
        active_nav="mashhad",
        meta_title="سفارش گل و ارسال در مشهد | زاد",
        meta_description="مرکز سفارش گل زاد در مشهد برای ارسال همان‌روز، بررسی موجودی و هماهنگی سریع.",
        breadcrumbs=breadcrumbs,
        enable_product_modal=True,
        content_page="mashhad",
        suppress_default_hero=not db_hero,
    )

    if db_hero:
        context.update(db_hero)

    context.update(
        {
            "curated_items": curated_items,
            "lead_form": LeadRequestForm(initial_lead_type="flower"),
            "lead_default_type": "flower",
        }
    )

    return render(request, "main/pages/local/hub.html", context)

def _occasion_links(limit=4):
    return [
        {
            "label": tag.name,
            "url": reverse("occasion_detail", args=[tag.slug]),
        }
        for tag in _active_occasion_tags(limit=limit)
    ]

def _local_landing(request, landing_type):
    if landing_type == "order":
        title = "سفارش گل در مشهد"
        subtitle = "انتخاب گل باکیفیت و هماهنگی سریع و شفاف برای ارسال در مشهد."
        meta_title = "سفارش گل در مشهد | زاد"
        meta_description = "سفارش گل در مشهد با پاسخ‌گویی سریع، چیدمان اختصاصی و هماهنگی تلفنی زاد."
    elif landing_type == "delivery":
        title = "ارسال همان‌روز گل در مشهد"
        subtitle = "هماهنگی ارسال همان‌روز با بسته‌بندی و استانداردهای زاد."
        meta_title = "ارسال همان‌روز گل در مشهد | زاد"
        meta_description = "ارسال همان‌روز گل در مشهد با پشتیبانی تلفنی و انتخاب از محصولات آماده زاد."
    else:
        raise Http404("Landing page not found")

    curated_items = list(
        _published_products_for_section(Category.Section.FLOWERS).order_by(
            "-featured",
            "sort_order",
            "-created_at",
        )[:8]
    )

    local_faq = [
        {
            "question": "کدام محدوده‌های مشهد برای سفارش فوری پوشش داده می‌شوند؟",
            "answer": "بیشتر محدوده‌های شهری مشهد در ساعات کاری قابل بررسی‌اند و امکان دقیق پس از دریافت نشانی تأیید می‌شود.",
        },
        {
            "question": "برای ارسال همان‌روز چقدر زودتر هماهنگ کنم؟",
            "answer": "بهتر است حداقل دو تا سه ساعت زودتر پیام بدهید؛ امکان نهایی به موجودی و ظرفیت آماده‌سازی بستگی دارد.",
        },
        {
            "question": "آیا قبل از ارسال تصویر نهایی را دریافت می‌کنم؟",
            "answer": "در صورت درخواست، امکان هماهنگی برای ارسال تصویر نهایی پیش از تحویل وجود دارد.",
        },
    ]

    breadcrumbs = _with_home(
        [
            {"name": "Mashhad Orders", "url": reverse("mashhad_hub")},
            {"name": title, "url": None},
        ]
    )

    context = _default_context(
        request,
        page_type="local",
        active_nav="mashhad",
        meta_title=meta_title,
        meta_description=meta_description,
        breadcrumbs=breadcrumbs,
        enable_product_modal=True,
        content_page="mashhad",
    )

    hero_data = _hero_from_key("mashhad", title=title, text=subtitle)
    target_slug = {
        "order": "flower-order",
        "delivery": "flower-delivery",
    }[landing_type]
    db_hero = _get_site_hero("mashhad", target_slug)

    if db_hero:
        hero_data = db_hero

    context.update(hero_data)

    occasion_links = _occasion_links(limit=4)

    if not occasion_links:
        occasion_links = [
            _category_card(category)
            for category in _active_categories_for_section(Category.Section.FLOWERS)[:4]
        ]

    context.update(
        {
            "landing_title": title,
            "landing_subtitle": subtitle,
            "curated_items": curated_items,
            "why_zad": [
                "چیدمان مینیمال و متناسب با مناسبت",
                "پاسخ‌گویی سریع و هماهنگی شفاف پیش از ارسال",
                "امکان ارسال همان‌روز در محدوده‌های قابل پوشش مشهد",
                "بسته‌بندی حرفه‌ای و آماده هدیه",
            ],
            "occasion_links": occasion_links,
            "lead_form": LeadRequestForm(initial_lead_type="flower"),
            "lead_default_type": "flower",
        }
    )

    return render(request, "main/pages/local/landing.html", context)

def mashhad_flower_order(request):
    return _local_landing(request, "order")

def mashhad_flower_delivery(request):
    return _local_landing(request, "delivery")
