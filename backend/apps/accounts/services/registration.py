"""Signing up, and the one account field a person may change afterwards.

An account here is an **email address and a password**, and nothing else. The
address is what signs somebody back in and the only way back into an account
whose password has been forgotten; the *display name* — the thing printed on
every scoreboard — belongs to ``players.Player`` and is chosen on its own screen
straight after. Keeping the two apart is the point: a published name must never
be half of a credential.
"""

from __future__ import annotations

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction

from apps.accounts.models import User
from apps.core_common.exceptions import Conflict, ValidationFailed
from apps.players.services import ensure_player_for_user
from shared.logging import get_logger, labels

logger = get_logger(__name__)


def normalize_email(*, email: str | None) -> str | None:
    """Trim and lower-case an address; ``None`` means "not given".

    Lower-cased in full, not only the domain: addresses are compared
    case-insensitively everywhere here (sign-in, the social adapter's
    ``email__iexact``), and storing them one way is what keeps the plain unique
    constraint agreeing with those comparisons.
    """
    email = (email or "").strip().lower()
    return email or None


def _validate_password(*, password: str, user: User) -> None:
    """Run ``AUTH_PASSWORD_VALIDATORS`` as one readable refusal.

    ``user`` is passed so ``UserAttributeSimilarityValidator`` can see the
    address the password must not simply repeat.
    """
    try:
        validate_password(password, user=user)
    except DjangoValidationError as exc:
        raise ValidationFailed(" ".join(exc.messages), code="invalid_password") from exc


def _validate_email_free(*, email: str, exclude_user: User | None = None) -> None:
    taken = User.objects.filter(email__iexact=email)
    if exclude_user is not None:
        taken = taken.exclude(pk=exclude_user.pk)
    if taken.exists():
        raise ValidationFailed(
            "An account already uses that email address.", code="email_taken"
        )


@transaction.atomic
def register_user(*, email: str, password: str, full_name: str = "") -> User:
    """Create an account and the competitor that goes with it.

    **Everything is validated before anything is written**, so a refusal never
    leaves a ``User`` behind without its ``Player`` — and the two writes share
    one transaction, so neither can survive the other failing.

    The address is required *here* rather than on the column: accounts made
    another way (a shell script, a fixture) may have none and nothing about
    them stops working. What it buys is a way back in.
    """
    email = normalize_email(email=email)
    full_name = (full_name or "").strip()

    if email is None:
        raise ValidationFailed(
            "Enter an email address. It is how you get back in if you forget "
            "your password.",
            code="email_required",
        )
    _validate_email_free(email=email)
    _validate_password(password=password, user=User(email=email, full_name=full_name))

    try:
        user = User.objects.create_user(
            email=email, password=password, full_name=full_name
        )
    except IntegrityError as exc:
        # Two signups claiming the same address in the same instant: the check
        # above saw it free, the constraint did not.
        raise Conflict(
            "An account already uses that email address.", code="email_taken"
        ) from exc

    player = ensure_player_for_user(user=user)
    logger.info(
        "User registered",
        user=labels.user(user),
        player=labels.player(player),
        auth_method="password",
    )
    return user


def set_email(*, user: User, email: str) -> User:
    """Add or change the caller's address.

    Changing one is offered; **clearing one is not**. The address is how a
    Google sign-in finds this account again, and for a staff account it is the
    only thing the admin's own login form keys on — so removing it can silently
    take a door away, which is not a thing to do through a blank field.
    """
    address = normalize_email(email=email)
    if address is None:
        raise ValidationFailed(
            "Enter an email address. One already on the account can be changed, "
            "but not removed.",
            code="email_required",
        )
    _validate_email_free(email=address, exclude_user=user)

    user.email = address
    try:
        user.save(update_fields=["email", "updated_at"])
    except IntegrityError as exc:
        raise Conflict(
            "That email address was just taken.", code="email_taken"
        ) from exc
    logger.info("Email changed", user=labels.user(user))
    return user
