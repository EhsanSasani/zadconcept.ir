"""Admin registration facade.

Importing this package registers every existing model once and preserves the
historical ``main.admin`` form imports used by tests and integrations.
"""

from .legacy import *  # noqa: F401,F403
