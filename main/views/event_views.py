from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone

from ..forms import LeadRequestForm
from ..managed_heroes import _get_site_hero
from ..models import Event, PublishStatus, WorkshopPageContent
from ..page_context import _default_context, _with_home
from ..page_presentation import _hero_from_key
from ..seo import event_node


def events(request):
    published_events = Event.objects.filter(
        status=PublishStatus.PUBLISHED,
        end_at__gte=timezone.now(),
    ).order_by("start_at", "-created_at")

    breadcrumbs = _with_home([{"name": "ورکشاپ‌ها", "url": None}])

    context = _default_context(
        request,
        page_type="workshops",
        active_nav="events",
        meta_title="ورکشاپ‌های خلاق و تجربه‌محور زاد در مشهد",
        meta_description=(
            "اطلاعات و ثبت درخواست ورکشاپ‌های عمومی، خصوصی و سازمانی زاد "
            "در مشهد؛ تجربه‌ای عملی برای ساختن، انتخاب‌کردن و خلق اثری شخصی."
        ),
        breadcrumbs=breadcrumbs,
    )

    page_hero = _get_site_hero("events")
    workshop_copy = WorkshopPageContent.current() or WorkshopPageContent()

    if page_hero:
        context.update(page_hero)

    context.update(
        {
            "workshops_hero_kicker": (
                page_hero["page_hero_kicker"]
                if page_hero
                else "ZAD WORKSHOPS"
            ),
            "workshops_hero_title": (
                page_hero["page_hero_title"]
                if page_hero
                else "ورکشاپ‌های زاد"
            ),
            "workshops_hero_text": (
                page_hero["page_hero_text"]
                if page_hero
                else (
                    "فضایی برای کار با دست‌ها، انتخاب و ترکیب متریال "
                    "و ساختن اثری شخصی در کنار دیگران."
                )
            ),
            "workshops_hero_image": (
                page_hero["page_hero_image"]
                if page_hero
                else "main/img/workshops-hero.webp"
            ),
            "workshops_hero_mobile_image": (
                page_hero["page_hero_mobile_image"] if page_hero else ""
            ),
            "events": published_events,
            "workshop_copy": workshop_copy,
            "lead_form": LeadRequestForm(
                initial_lead_type="event",
                include_event_fields=True,
            ),
            "lead_default_type": "event",
        }
    )

    return render(request, "main/pages/workshops/index.html", context)


def event_detail(request, slug: str):
    event = get_object_or_404(
        Event,
        slug=slug,
        status=PublishStatus.PUBLISHED,
    )

    breadcrumbs = _with_home(
        [
            {"name": "Events", "url": reverse("events")},
            {"name": event.title, "url": None},
        ]
    )

    context = _default_context(
        request,
        page_type="category",
        active_nav="events",
        meta_title=f"{event.title} | ورکشاپ زاد",
        meta_description=f"جزئیات، زمان، مکان و هماهنگی حضور در {event.title} از ورکشاپ‌های زاد.",
        breadcrumbs=breadcrumbs,
        content_page="event-detail",
        og_type="article",
        social_image=event.cover_image if event.cover_image else None,
    )

    hero_data = _hero_from_key(
        "events",
        title=event.title,
        text=event.description,
        image=event.cover_image.url if event.cover_image else "main/img/hero-events.webp",
    )

    db_hero = _get_site_hero("events", event.slug)

    if db_hero:
        hero_data = db_hero

    context.update(hero_data)

    context.update(
        {
            "event": event,
            "lead_form": LeadRequestForm(
                initial_lead_type="event",
                include_event_fields=True,
            ),
            "lead_default_type": "event",
        }
    )

    context["structured_data_graph"].append(event_node(event))

    return render(request, "main/pages/workshops/detail.html", context)
