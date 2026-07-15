from django.db import migrations


GLOBAL_HERO_TARGETS = (
    "flowers",
    "bakery",
    "gifts",
    "contact",
    "faq",
    "about",
)


def normalize_global_hero_targets(apps, schema_editor):
    """Make previously unreachable whole-page Hero records visible.

    Older admin forms allowed a target slug for pages such as Flowers even
    though those pages only read the blank-slug Hero. Renumbering all records
    through a temporary range avoids collisions with the existing uniqueness
    constraint while preserving their display order.
    """

    SiteHero = apps.get_model("main", "SiteHero")

    for target_page in GLOBAL_HERO_TARGETS:
        heroes = list(
            SiteHero.objects.filter(target_page=target_page).order_by(
                "sort_order",
                "id",
            )
        )
        if not heroes or not any(hero.target_slug for hero in heroes):
            continue

        temporary_start = max(hero.sort_order for hero in heroes) + len(heroes) + 1000

        for index, hero in enumerate(heroes):
            SiteHero.objects.filter(pk=hero.pk).update(
                sort_order=temporary_start + index,
            )

        for index, hero in enumerate(heroes):
            SiteHero.objects.filter(pk=hero.pk).update(
                target_slug="",
                sort_order=index * 10,
            )


class Migration(migrations.Migration):
    dependencies = [
        ("main", "0014_v14_followup"),
    ]

    operations = [
        migrations.RunPython(
            normalize_global_hero_targets,
            migrations.RunPython.noop,
        ),
    ]
