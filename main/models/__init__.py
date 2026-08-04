"""Stable model and migration facade for the ``main`` Django app.

Historical migrations serialize several callbacks as ``main.models.*``.  The
facade keeps those paths stable while model domains move into dedicated files.
"""

from .legacy import *  # noqa: F401,F403


_MIGRATION_CALLBACKS = (
    category_cover_upload_to,
    event_cover_upload_to,
    hero_font_upload_to,
    home_hero_mobile_upload_to,
    home_hero_upload_to,
    news_cover_upload_to,
    product_cover_upload_to,
    product_gallery_upload_to,
    site_hero_mobile_upload_to,
    site_hero_upload_to,
    tag_cover_upload_to,
    validate_hero_font_file_size,
)

for _callback in _MIGRATION_CALLBACKS:
    _callback.__module__ = __name__

del _callback
