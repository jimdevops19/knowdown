"""The numbers the account door is measured against."""

from __future__ import annotations

#: Mirrors ``AUTH_PASSWORD_VALIDATORS``' ``MinimumLengthValidator`` in
#: ``config/settings/base.py``. Kept here as well so the serializer, the help
#: text and the check are one edit rather than three.
PASSWORD_MIN_LENGTH = 8

#: Not a security limit — a hash is fixed-length whatever goes into it — but a
#: guard on the *work*: every sign-in attempt hashes what it is given, so an
#: unbounded field is a way to spend CPU by the megabyte. Also the "you have
#: pasted something that isn't your password" case.
PASSWORD_MAX_LENGTH = 128
