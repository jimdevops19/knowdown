"""URLconf for the gate tests — the admin at a known prefix, nothing else.

The real root URLconf mounts the admin only when ADMIN_ENABLED, and reads
ADMIN_URL at import time, so a test that wants a real admin behind the gate has
to point ROOT_URLCONF somewhere the mount is unconditional.
"""

from django.contrib import admin
from django.urls import path

urlpatterns = [path("admin/", admin.site.urls)]
