from django.apps import AppConfig


# --- پیکربندی پایه اپ اصلی فروشگاه ---
class MainConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "main"
    verbose_name = "محتوای فروشگاه"

    def ready(self):
        from . import signals  # noqa: F401
        from . import video_pipeline  # noqa: F401
