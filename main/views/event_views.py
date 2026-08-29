from django.shortcuts import get_object_or_404, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone

from ..forms import LeadRequestForm
from ..managed_heroes import _get_site_hero
from ..models import (
    Event,
    PublishStatus,
    WorkshopGalleryImage,
    WorkshopPageContent,
)
from ..page_context import _default_context, _with_home
from ..page_presentation import _hero_from_key
from ..seo import event_node


WORKSHOP_GALLERY_FALLBACKS = (
    ("main/img/workshops-story.webp", "لحظه‌ای از ورکشاپ‌های زاد"),
    ("main/img/workshop-event-01.webp", "گل‌آرایی در ورکشاپ زاد"),
    ("main/img/workshop-type-public.webp", "تجربه ساختن در ورکشاپ زاد"),
    ("main/img/workshop-event-02.webp", "جزئیات یک ورکشاپ زاد"),
    ("main/img/workshop-type-private.webp", "شرکت‌کنندگان ورکشاپ زاد"),
    ("main/img/workshop-type-corporate.webp", "دورهمی ورکشاپ زاد"),
)


def _workshop_gallery_items():
    gallery_items = []

    for gallery_image in (
        WorkshopGalleryImage.objects.filter(is_active=True)
        .select_related("event")
        .order_by("sort_order", "id")[:6]
    ):
        try:
            image_url = gallery_image.image.url
        except (OSError, ValueError):
            continue

        gallery_items.append(
            {
                "url": image_url,
                "alt": (
                    gallery_image.alt_text
                    or (gallery_image.event.title if gallery_image.event else "")
                    or "لحظه‌ای از ورکشاپ‌های زاد"
                ),
                "event": gallery_image.event,
            }
        )

    for image_path, alt_text in WORKSHOP_GALLERY_FALLBACKS[len(gallery_items):]:
        gallery_items.append(
            {
                "url": static(image_path),
                "alt": alt_text,
                "event": None,
            }
        )

    return gallery_items[:6]


def events(request):
    published_events = list(
        Event.objects.filter(
            status=PublishStatus.PUBLISHED,
            end_at__gte=timezone.now(),
        ).order_by("start_at", "-created_at")[:3]
    )

    breadcrumbs = _with_home([{"name": "ورکشاپ‌ها", "url": None}])

    context = _default_context(
        request,
        page_type="workshops",
        active_nav="events",
        meta_title="ورکشاپ‌های زاد در مشهد | آموزشی، تجربه‌محور و دورهمی",
        meta_description=(
            "ورکشاپ‌های آموزشی، تجربه‌محور و دورهمی زاد در مشهد؛ "
            "مشاهده برنامه‌های پیش رو، گالری ورکشاپ‌های برگزارشده و ثبت درخواست برگزاری."
        ),
        breadcrumbs=breadcrumbs,
        suppress_default_hero=True,
    )

    page_hero = _get_site_hero("events")
    workshop_copy = WorkshopPageContent.current() or WorkshopPageContent()

    context.update(
        {
            "workshops_hero_title": "ورکشاپ‌های زاد",
            "workshops_hero_text": "یاد بگیر، تجربه کن، کنار هم باش.",
            "workshops_hero_image": (
                page_hero["page_hero_image"]
                if page_hero
                else "main/img/workshops-hero.webp"
            ),
            "workshops_hero_mobile_image": (
                page_hero["page_hero_mobile_image"] if page_hero else ""
            ),
            "events": published_events,
            "gallery_items": _workshop_gallery_items(),
            "workshop_copy": workshop_copy,
            "lead_form": LeadRequestForm(
                initial_lead_type="event",
                include_event_fields=True,
            ),
            "lead_default_type": "event",
        }
    )

    return render(request, "main/pages/workshops/redesign.html", context)


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
