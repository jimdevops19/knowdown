from django.apps import AppConfig


class TesterConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.tester"
    verbose_name = "Question tester"
