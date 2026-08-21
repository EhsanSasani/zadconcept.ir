from django.shortcuts import render

from .forms import LeadRequestForm
from .managed_heroes import _get_site_hero
from .page_context import _default_context, _with_home
from .page_presentation import _hero_from_key
from .site_content import FAQ_PAGE_GROUPS, FAQ_PAGE_ITEMS


def contact(request):
    breadcrumbs = _with_home([{"name": "Contact", "url": None}])

    context = _default_context(
        request,
        page_type="contact",
        active_nav="",
        meta_title="تماس با زاد | هماهنگی سفارش و ارسال",
        meta_description="تماس با زاد برای سفارش، مشاوره، بررسی موجودی و هماهنگی زمان ارسال در مشهد.",
        breadcrumbs=breadcrumbs,
    )

    hero_data = _hero_from_key("contact")
    db_hero = _get_site_hero("contact")

    if db_hero:
        hero_data = db_hero

    context.update(hero_data)
    context.update(
        {
            "lead_form": LeadRequestForm(initial_lead_type="flower"),
            "lead_default_type": "flower",
        }
    )

    return render(request, "contact.html", context)


def faq(request):
    breadcrumbs = _with_home([{"name": "FAQ", "url": None}])

    context = _default_context(
        request,
        page_type="category",
        active_nav="",
        meta_title="سوالات متداول سفارش و ارسال | زاد",
        meta_description="پاسخ سوالات متداول درباره سفارش محصولات زاد، ارسال، ساعت کاری و هماهنگی ورکشاپ‌ها.",
        breadcrumbs=breadcrumbs,
        faq_items=FAQ_PAGE_ITEMS,
        include_faq_schema=True,
        content_page="faq",
    )

    hero_data = _hero_from_key("faq")
    db_hero = _get_site_hero("faq")

    if db_hero:
        hero_data = db_hero

    context.update(hero_data)
    context["faq_page_groups"] = FAQ_PAGE_GROUPS

    return render(request, "faq.html", context)


def about(request):
    breadcrumbs = _with_home([{"name": "About", "url": None}])

    context = _default_context(
        request,
        page_type="about",
        active_nav="about",
        meta_title="درباره زاد | گل، سوئیت‌بار و ورکشاپ در مشهد",
        meta_description="با فضای واقعی زاد، گل‌ها، سوئیت‌بار و ورکشاپ‌های خلاقانه زاد در مشهد آشنا شوید.",
        breadcrumbs=breadcrumbs,
    )

    hero_data = _hero_from_key("about")
    db_hero = _get_site_hero("about")

    if db_hero:
        hero_data = db_hero

    context.update(hero_data)
    context.update(
        {
            "about_hero_kicker": (
                db_hero["page_hero_kicker"]
                if db_hero
                else "ZAD CONCEPT STORE · MASHHAD"
            ),
            "about_hero_title": (
                db_hero["page_hero_title"]
                if db_hero
                else "زاد؛ جایی برای گل، طعم، هدیه و تجربه."
            ),
            "about_hero_text": (
                db_hero["page_hero_text"]
                if db_hero
                else "یک فضای واقعی برای انتخاب‌های دقیق؛ از گل‌های روز و سوئیت‌بار تا ورکشاپ‌هایی که آدم‌ها را دور یک میز جمع می‌کنند."
            ),
            "about_hero_image": (
                db_hero["page_hero_image"]
                if db_hero
                else "main/img/about/zad-floral-wall-v1.webp"
            ),
            "about_hero_mobile_image": (
                db_hero["page_hero_mobile_image"] if db_hero else ""
            ),
        }
    )

    return render(request, "about.html", context)
