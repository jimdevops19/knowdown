"""Forgot password: email a link, then spend it once.

Split from ``registration.py`` because the two halves answer different
questions. ``request_password_reset`` decides — silently — whether an address
gets an email at all; ``reset_password`` spends a link somebody already holds.
The request half is the one that matters: it must look identical from outside
whether or not the address names an account, and this module is what makes that
claim true rather than merely the view's intention.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from apps.accounts.models import User
from apps.core_common.exceptions import ValidationFailed
from shared.logging import get_logger, labels

from .registration import normalize_email

logger = get_logger(__name__)


def request_password_reset(*, email: str) -> None:
    """Email a reset link if — and only if — the address can use one.

    Answers nothing to the caller either way: the view returns the same generic
    response whatever happens here, so this is the one place that branches on
    "does this account exist", and every way that can be "no" (no such row, an
    inactive account, or one signed in only through Google and therefore
    holding an unusable password) takes the same silent early return.

    Nothing is logged by address either — a line reading "no account for
    x@y.com" would just move the oracle from the response into the log file.
    """
    address = normalize_email(email=email)
    if address is None:
        return
    try:
        user = User.objects.get(email__iexact=address, is_active=True)
    except User.DoesNotExist:
        return
    if not user.has_usable_password():
        return
    _send_reset_email(user=user)


def _send_reset_email(*, user: User) -> None:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    # Built from a setting, never from the request: which Host reached this API
    # is a routing detail, not a fact about which client can complete a token.
    reset_url = (
        f"{settings.FRONTEND_URL.rstrip('/')}/reset-password?uid={uid}&token={token}"
    )
    body = render_to_string(
        "accounts/email/password_reset_email.txt",
        {"reset_url": reset_url, "user": user},
    )
    try:
        send_mail(
            subject="Reset your Knowdown password",
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
    except Exception:
        # A broken or slow relay must not turn "this address has an account"
        # into a 500 the caller can tell apart from the silent 200 an unknown
        # address gets — which is the very oracle this module exists to deny.
        # `fail_silently=False` stays on purpose: we *want* the raise, so it can
        # be logged here (with the request id) rather than vanishing.
        logger.exception("Password reset email failed to send", user=labels.user(user))
        return
    logger.info("Password reset email sent", user=labels.user(user))


def reset_password(*, uidb64: str, token: str, new_password: str) -> User:
    """Spend a reset link: verify it, then set the new password.

    ``default_token_generator`` folds the password hash and ``last_login`` into
    the token it checks, so a link stops working the moment either changes —
    used once, overtaken by a newer reset, or by a password changed some other
    way since. Nothing extra needs revoking because of that. Expiry is Django's
    own ``PASSWORD_RESET_TIMEOUT``.
    """
    user = _user_from_uidb64(uidb64=uidb64)
    if user is None or not default_token_generator.check_token(user, token):
        raise ValidationFailed(
            "This password reset link is invalid or has expired. Request a new one.",
            code="invalid_reset_token",
        )
    try:
        validate_password(new_password, user=user)
    except DjangoValidationError as exc:
        raise ValidationFailed(" ".join(exc.messages), code="invalid_password") from exc

    user.set_password(new_password)
    user.save(update_fields=["password", "updated_at"])
    logger.info("Password reset completed", user=labels.user(user))
    return user


def _user_from_uidb64(*, uidb64: str) -> User | None:
    try:
        pk = urlsafe_base64_decode(uidb64).decode()
        return User.objects.get(pk=pk, is_active=True)
    except (
        TypeError,
        ValueError,
        OverflowError,
        DjangoValidationError,
        User.DoesNotExist,
    ):
        return None
