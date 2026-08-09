"""Public view facade.

URL configuration, the custom 404 handler, and a small number of historical
imports rely on ``main.views``.  Keep that import path stable while individual
domains are extracted from :mod:`main.views.legacy`.
"""

from .support import *  # noqa: F401,F403
from .blog import blog, blog_detail
from .catalog import (
    bakery,
    bakery_all,
    bakery_subcategory,
    flower_occasion,
    flower_subcategory,
    flowers,
    flowers_all,
    flowers_same_day,
    gift_subcategory,
    gifts,
    gifts_all,
)
from .content import (
    about,
    contact,
    faq,
    international_orders,
    international_orders_en,
    policy_page,
)
from .home import index
from .leads import submit_lead_request
from .local import mashhad_flower_delivery, mashhad_flower_order, mashhad_hub
from .occasions import occasion_detail, occasions
from .products import (
    bakery_product_detail,
    flower_detail,
    flower_detail_redirect,
    flower_product_detail,
    gift_product_detail,
    product_detail,
)
from .system import csp_report, custom_404, indexnow_key, robots_txt
from .weddings import wedding_collection, weddings
from .workshops import event_detail, events
