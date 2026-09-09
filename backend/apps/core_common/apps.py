from django.apps import AppConfig


class CoreCommonConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core_common"
    label = "core_common"
    verbose_name = "Core (shared)"
