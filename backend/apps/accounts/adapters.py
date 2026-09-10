"""allauth adapters — the social half of the account guarantees.

Registration provisions a ``Player`` in ``services.register_user``; a social
signup never goes through that service, so the same guarantee is made here
instead. Without it a Google-created account would have a login and no
competitor, which is an account that cannot play.

``pre_social_login`` also handles the two cases where allauth would otherwise
*decline* to auto-create the account and fall back to its interactive signup
form — a form this API-only deployment does not route, so the fallback would
crash the request with ``NoReverseMatch``.
"""

from __future__ import annotations

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter

from apps.accounts.models import User
from apps.core_common.exceptions import ValidationFailed
from apps.players.services import ensure_player_for_user
from shared.logging import get_logger, labels

logger = get_logger(__name__)


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        """Keep every Google sign-in on the auto-signup path.

        allauth auto-creates an account only when the provider handed over an
        address nobody else holds. Both ways that fails end in a redirect to a
        page this API does not serve, so both are answered here instead:

        * **No address.** Google's consent screen lets somebody untick the
          email permission even though we ask for it. Nothing to do but say so,
          naming the checkbox they need to tick.
        * **The address already belongs to a local account** — typically one
          made before Google sign-in existed, or a superuser created from the
          shell. Google has verified the address, so its owner is the person in
          front of us: link the two rather than lock them out. Only for a
          *verified* address — an unverified one is a claim, and honouring it
          would let anyone type their way into somebody else's account.
        """
        super().pre_social_login(request, sociallogin)
        if sociallogin.is_existing:
            return  # A known Google account: allauth signs them straight in.

        address = sociallogin.email_addresses[0] if sociallogin.email_addresses else None
        if not address or not address.email:
            logger.warning("Google sign-in without an email address", auth_method="google")
            raise ValidationFailed(
                "Google didn't share your email address, which Knowdown needs to "
                "create your account. Sign in again and allow the email permission.",
                code="google_email_permission_required",
            )

        existing = User.objects.filter(email__iexact=address.email).first()
        if not existing:
            return  # Nobody holds it: allauth's own auto-signup takes over.

        if not address.verified:
            raise ValidationFailed(
                "A Knowdown account already uses this email address, and Google "
                "hasn't verified that it's yours.",
                code="email_already_registered",
            )

        sociallogin.connect(request, existing)
        # `save_user` below is the signup path only, so the Player guarantee it
        # makes has to be repeated here: an account made with `createsuperuser`
        # has never had one.
        player = ensure_player_for_user(user=existing)
        logger.info(
            "Linked Google account to existing user",
            user=labels.user(existing),
            player=labels.player(player),
            auth_method="google",
        )

    def populate_user(self, request, sociallogin, data):
        """Seed ``full_name`` from the provider's profile claims.

        The *display name* is deliberately not seeded from anything Google
        sends: it is published on every scoreboard, and a real name arriving
        there because somebody pressed a button is not a choice they made.
        """
        user = super().populate_user(request, sociallogin, data)
        if not user.full_name:
            name = data.get("name") or " ".join(
                part for part in (data.get("first_name"), data.get("last_name")) if part
            )
            user.full_name = (name or "").strip()
        return user

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form=form)
        player = ensure_player_for_user(user=user)
        logger.info(
            "User registered",
            user=labels.user(user),
            player=labels.player(player),
            auth_method="google",
        )
        return user
