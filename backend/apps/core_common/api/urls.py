from django.urls import path

from .views import LivenessView, ReadinessView

app_name = "core_common"

urlpatterns = [
    # Readiness (DB-backed) also answers at the plain health path; liveness is
    # process-only. See the views for why the two must not be the same check.
    path("health/", ReadinessView.as_view(), name="health"),
    path("health/ready/", ReadinessView.as_view(), name="health-ready"),
    path("health/live/", LivenessView.as_view(), name="health-live"),
]
