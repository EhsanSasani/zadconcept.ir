"""Content HTTP views.

Extracted from the historical view module; shared presentation policy remains in
``main.views.legacy`` until its dedicated lower layer is complete.
"""

from ..forms import LeadRequestForm

from .support import (
    FAQ_PAGE_GROUPS,
    FAQ_PAGE_ITEMS,
    Http404,
    INTERNATIONAL_FAQ_EN,
    INTERNATIONAL_FAQ_FA,
    POLICY_PAGES,
    _default_context,
    _get_site_hero,
    _hero_from_key,
    _with_home,
    render,
    reverse,
    settings,
)

def contact(request):
    breadcrumbs = _with_home([{"name": "Contact", "url": None}])

    context = _default_context(
        request,
        page_type="contact",
        active_nav="",
        meta_title="تماس با زاد | هماهنگی سفارش و ارسال",
        meta_description="تماس با زاد برای سفارش، مشاوره، بررسی موجودی و هماهنگی زمان ارسال در مشهد.",
        breadcrumbs=breadcrumbs,
        content_page="contact",
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
        content_page="about",
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

def _normalized_policy(policy):
    """Return template-safe policy data, including explicit empty item lists."""

    normalized_sections = []
    for section in policy.get("sections", []):
        paragraphs = section.get("paragraphs") or []
        items = section.get("items") or []
        if isinstance(paragraphs, str):
            paragraphs = [paragraphs]
        if isinstance(items, str):
            items = [items]
        normalized_sections.append(
            {
                "title": section.get("title", ""),
                "paragraphs": list(paragraphs),
                # The explicit key prevents Django templates from resolving the
                # missing value to dict.items(), which rendered raw tuples.
                "items": list(items),
            }
        )

    return {**policy, "sections": normalized_sections}

def policy_page(request, policy_slug):
    policy = POLICY_PAGES.get(policy_slug)
    if not policy:
        raise Http404("Policy page not found")

    breadcrumbs = _with_home([{"name": policy["title"], "url": None}])
    context = _default_context(
        request,
        page_type="policy",
        active_nav="",
        meta_title=policy["meta_title"],
        meta_description=policy["meta_description"],
        breadcrumbs=breadcrumbs,
        suppress_default_hero=True,
    )
    context["policy"] = _normalized_policy(policy)
    return render(request, "policy_page.html", context)

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
        suppress_default_hero=True,
    )
    return render(request, "international_orders.html", context)

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
        hide_global_chrome=True,
        suppress_default_hero=True,
    )
    return render(request, "international_orders_en.html", context)
