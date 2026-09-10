"""The write side of an account: making one, correcting it, resetting it.

``lockout`` is imported as a module rather than re-exported function by
function: its three calls (``guard``/``record_failure``/``record_success``) read
as one mechanism at the call site (``lockout.guard(...)``), and it is the only
service here a *test* wants to reach past.
"""

from . import lockout
from .password_reset import request_password_reset, reset_password
from .registration import normalize_email, register_user, set_email

__all__ = [
    "lockout",
    "normalize_email",
    "register_user",
    "request_password_reset",
    "reset_password",
    "set_email",
]
