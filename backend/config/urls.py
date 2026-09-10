"""Root URL configuration.

Everything a client consumes lives under a version prefix (``/api/v1/``). The
prefix is the single seam where a future ``v2`` can be introduced without
breaking existing clients. Each app owns its own ``api/urls.py``.
"""

import re

from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve as serve_static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

api_v1_patterns = [
    path("", include("apps.core_common.api.urls")),
    path("categories/", include("apps.categories.api.urls")),
    path("auth/", include("apps.accounts.api.urls")),
    path("players/", include("apps.players.api.urls")),
]

urlpatterns = [
    path("api/v1/", include((api_v1_patterns, "v1"))),
]

# Django admin — off unless the tier asks for it, and never at `/admin/`.
# `settings.ADMIN_URL` is a random 40-character prefix unless one is configured
# (see shared.admin_url); `manage.py runserver` prints it.
if settings.ADMIN_ENABLED:
    urlpatterns += [path(settings.ADMIN_URL, admin.site.urls)]

# OpenAPI schema + interactive docs — development only. Mounted anywhere else
# they hand anyone the full API map instead of making them guess it, and nothing
# at runtime needs them: `manage.py spectacular` writes the same document
# offline.
if settings.DEBUG:
    urlpatterns += [
        path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
        path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    ]

# No object storage yet, so Django serves uploads itself — question images, and
# later player avatars. NOT `django.conf.urls.static.static()`, which no-ops
# unless DEBUG: uploads would then write fine and 404 on read. Built by hand
# instead, with the same regex that helper would use.
urlpatterns += [
    re_path(
        r"^%s(?P<path>.*)$" % re.escape(settings.MEDIA_URL.lstrip("/")),
        serve_static,
        kwargs={"document_root": settings.MEDIA_ROOT},
    ),
]
