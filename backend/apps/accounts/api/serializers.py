"""The auth payloads.

Three of these carry an ``email`` field and all three are **write-only inputs**
— signing up, signing in, asking for a reset link. ``UserSerializer`` is the one
place an address is ever *emitted*, and it can only ever emit the caller's own
(``MeView.get_object`` returns ``request.user``). A test walks every serializer
in the API to keep that list at exactly four entries; see
``apps.accounts.tests.test_email_exposure``.
"""

from __future__ import annotations

from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.accounts import services as account_services
from apps.accounts.constants import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH
from apps.accounts.models import User
from apps.players import selectors as player_selectors


class UserSerializer(serializers.Serializer):
    """The signed-in identity: the account, plus the competitor behind it.

    A plain ``Serializer`` with an explicit field list, like the play-time
    serializers in ``apps.questions``: a ``ModelSerializer`` grows a field the
    day the *model* grows a column, and this is the one payload in the API where
    that would mean publishing a credential.

    The player fields ride along so a client needs one round trip rather than
    two — the top-right avatar and the name are wanted on every page. They stay
    nullable because a staff account may have no ``Player``.
    """

    id = serializers.UUIDField(read_only=True)
    email = serializers.EmailField(read_only=True)
    full_name = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)

    player_id = serializers.SerializerMethodField()
    player_name = serializers.SerializerMethodField()
    player_name_is_auto = serializers.SerializerMethodField()
    player_avatar_url = serializers.SerializerMethodField()
    player_mascot = serializers.SerializerMethodField()

    def update(self, instance: User, validated_data: dict) -> User:
        """Nothing on this payload is writable.

        The address used to be correctable here; it no longer is — it is
        fixed at signup, and ``services.set_email`` remains the only way to
        change one, for a shell to use on somebody's behalf.
        """
        return instance

    def _player(self, user: User):
        return player_selectors.player_for_user(user=user)

    def get_player_id(self, user: User) -> str | None:
        player = self._player(user)
        return str(player.id) if player is not None else None

    def get_player_name(self, user: User) -> str | None:
        player = self._player(user)
        return player.display_name if player is not None else None

    def get_player_name_is_auto(self, user: User) -> bool:
        """True while the name is one the platform generated — the client's cue
        to ask for a real one."""
        player = self._player(user)
        return bool(player is not None and player.has_auto_name)

    def get_player_avatar_url(self, user: User) -> str | None:
        player = self._player(user)
        return player_selectors.avatar_url(player=player) if player else None

    def get_player_mascot(self, user: User) -> str | None:
        """The mark they chose, or ``None`` for initials. Rides along for the
        same reason the name and the picture do: it is on every page."""
        player = self._player(user)
        return (player.mascot or None) if player else None


class AuthConfigSerializer(serializers.Serializer):
    """Which sign-in methods this deployment offers (see ``AuthConfigView``)."""

    password_enabled = serializers.BooleanField()
    google_enabled = serializers.BooleanField()


class RegisterSerializer(serializers.Serializer):
    """Signing up: an address, a password, and confirming it. Nothing else.

    Shape only. Whether the address is free and whether the password is strong
    enough are both decided in ``services.register_user`` — the same answers a
    later email change would give.

    The display name is deliberately not asked for here: it names the
    competitor, it is printed on every scoreboard, and it is chosen on its own
    screen straight after through ``PATCH /api/v1/players/me/``.
    """

    email = serializers.EmailField()
    password1 = serializers.CharField(
        write_only=True,
        min_length=PASSWORD_MIN_LENGTH,
        max_length=PASSWORD_MAX_LENGTH,
        style={"input_type": "password"},
    )
    password2 = serializers.CharField(
        write_only=True, style={"input_type": "password"}
    )

    def validate(self, attrs: dict) -> dict:
        if attrs["password1"] != attrs["password2"]:
            raise serializers.ValidationError(
                {"password2": "The two passwords don't match."}
            )
        return attrs

    def create(self, validated_data: dict) -> User:
        return account_services.register_user(
            email=validated_data["email"], password=validated_data["password1"]
        )


class LoginSerializer(serializers.Serializer):
    """Email + password. The address is the only thing it keys on.

    The display name is never accepted here: it is published in every ladder
    row, so accepting it as a login would hand anyone reading a scoreboard the
    half of the credential that is meant to be unguessable.

    ``email`` is a plain ``CharField``, not an ``EmailField``: everything that
    does not match an account has to be refused identically, and a malformed
    address answered with a 400 while an unknown one gets a 401 is a difference
    worth nothing to a person and everything to a script.

    The password is checked here rather than through ``authenticate()`` so the
    refusal, the timing and the log line are decided in one place.
    """

    email = serializers.CharField(write_only=True)
    password = serializers.CharField(
        write_only=True, max_length=PASSWORD_MAX_LENGTH, style={"input_type": "password"}
    )

    #: Said the same way whichever half is wrong. Which of the two it was is
    #: exactly what somebody working through a list of addresses wants to learn.
    REFUSAL = "No account matches that email and password."

    def validate(self, attrs: dict) -> dict:
        user = _user_by_email(email=attrs["email"])
        if user is None:
            # Hash anyway. Answering an unknown address faster than a wrong
            # password is itself an answer — it says the account exists.
            User().set_password(attrs["password"])
            raise AuthenticationFailed(self.REFUSAL, code="no_active_account")
        if not user.check_password(attrs["password"]) or not user.is_active:
            raise AuthenticationFailed(self.REFUSAL, code="no_active_account")

        refresh = TokenObtainPairSerializer.get_token(user)
        self.user = user
        return {"refresh": str(refresh), "access": str(refresh.access_token)}


class PasswordResetRequestSerializer(serializers.Serializer):
    """Shape only, for ``POST auth/password/reset/`` — an address, nothing else.

    Deliberately does not check whether the address belongs to an account: that
    check lives in ``services.password_reset`` precisely so it can answer
    nothing to the caller either way.
    """

    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    """The link's own uid and token, plus a new password typed twice.

    Strength is re-checked in the service rather than here:
    ``AUTH_PASSWORD_VALIDATORS`` needs the ``User`` the token names, and no
    lookup has happened at the point a serializer validates shape.
    """

    uid = serializers.CharField()
    token = serializers.CharField()
    new_password1 = serializers.CharField(
        write_only=True,
        min_length=PASSWORD_MIN_LENGTH,
        max_length=PASSWORD_MAX_LENGTH,
        style={"input_type": "password"},
    )
    new_password2 = serializers.CharField(
        write_only=True, style={"input_type": "password"}
    )

    def validate(self, attrs: dict) -> dict:
        if attrs["new_password1"] != attrs["new_password2"]:
            raise serializers.ValidationError(
                {"new_password2": "The two passwords don't match."}
            )
        return attrs


def _user_by_email(*, email: str) -> User | None:
    """Resolve a typed address to one account, or to nobody.

    Case-insensitive, like the rule that hands addresses out: they are stored
    lower-cased (``services.normalize_email``), so this and the column's unique
    constraint always agree on what "the same address" means.
    """
    email = (email or "").strip()
    if not email:
        return None
    return User.objects.filter(email__iexact=email).first()
