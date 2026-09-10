"""Thin views: parse input → call one service or selector → serialize."""

from __future__ import annotations

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core_common.exceptions import NotFound, ValidationFailed
from apps.players import selectors, services, validators

from .serializers import DisplayNameAvailabilitySerializer, PlayerMeSerializer


class PlayerMeView(APIView):
    """``GET``/``PATCH /api/v1/players/me/`` — the caller's own competitor.

    The PATCH is not a serializer ``update``: both writable things go through
    their service (``set_display_name``, ``set_avatar``), which is where the
    domain rules and the log lines live. The serializer's job here is to
    describe the *answer*, not to perform the write.
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_object(self):
        # Registration provisions one, and so does social sign-in — but an
        # account made another way (a shell script, `createsuperuser`) may
        # never have had one, and asking for it is a fine moment to make it.
        return services.ensure_player_for_user(user=self.request.user)

    @extend_schema(tags=["players"], responses=PlayerMeSerializer)
    def get(self, request, *args, **kwargs) -> Response:
        return Response(PlayerMeSerializer(self.get_object()).data)

    @extend_schema(tags=["players"], request=None, responses=PlayerMeSerializer)
    def patch(self, request, *args, **kwargs) -> Response:
        player = self.get_object()

        if "display_name" in request.data:
            player = services.set_display_name(
                player=player, display_name=str(request.data["display_name"])
            )
        # An `avatar` key holding nothing is how a picture is removed; a PATCH
        # that never mentions it leaves the one that is there alone.
        if "avatar" in request.FILES:
            player = services.set_avatar(player=player, image=request.FILES["avatar"])
        elif "avatar" in request.data and not request.data["avatar"]:
            player = services.set_avatar(player=player, image=None)

        return Response(PlayerMeSerializer(player).data)


class DisplayNameAvailableView(APIView):
    """``GET /api/v1/players/display-name-available/?display_name=…``

    A courtesy for the sign-up screen, not a gate: the claim itself is settled
    by ``set_display_name`` and, under a race, by the constraint underneath it.
    Answers about a *name*, never about a person — "taken" says a row holds it,
    and nothing about who.

    Authenticated, so it is not an anonymous way to enumerate which names exist.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["players"],
        parameters=[OpenApiParameter("display_name", str, required=True)],
        responses=DisplayNameAvailabilitySerializer,
    )
    def get(self, request, *args, **kwargs) -> Response:
        display_name = (request.query_params.get("display_name") or "").strip()
        if not display_name:
            raise ValidationFailed(
                "Ask about a name: ?display_name=…", code="display_name_required"
            )

        answer = {
            "display_name": display_name,
            "available": True,
            "reason": None,
            "message": None,
        }
        try:
            validators.validate_display_name(
                display_name=display_name,
                exclude_player=selectors.player_for_user(user=request.user),
            )
        except ValidationFailed as refusal:
            answer.update(
                available=False, reason=refusal.code, message=refusal.message
            )
        return Response(DisplayNameAvailabilitySerializer(answer).data)
