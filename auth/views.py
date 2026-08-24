"""Authentication views: hybrid token scheme.

- Access token: short-lived, returned in the JSON body, kept in memory by the
  frontend (never localStorage).
- Refresh token: httpOnly, Secure cookie scoped to ``.ecode2.com`` so it is
  shared across the Vercel frontend and the API subdomain. Rotated + blacklisted
  on every refresh.
- WS ticket: short-lived, single-use, for authenticating the audio WebSocket.
"""

from django.conf import settings
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from django.contrib.auth.models import User
from bookshelf.ws_auth import make_ws_ticket
from .serializers import UserSerializer, CustomTokenObtainPairSerializer


def _set_refresh_cookie(response, refresh_token: str):
    max_age = int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds())
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=max_age,
        httponly=True,
        secure=settings.REFRESH_COOKIE_SECURE,
        samesite=settings.REFRESH_COOKIE_SAMESITE,
        domain=settings.COOKIE_DOMAIN,
        path="/",
    )


def _clear_refresh_cookie(response):
    response.delete_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        domain=settings.COOKIE_DOMAIN,
        path="/",
    )


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.AllowAny]


class CustomTokenObtainPairView(TokenObtainPairView):
    """Login: set the refresh cookie, return only the access token in the body."""

    serializer_class = CustomTokenObtainPairSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        refresh = response.data.pop("refresh", None)
        if refresh:
            _set_refresh_cookie(response, refresh)
        return response


class CookieTokenRefreshView(TokenRefreshView):
    """Silent refresh: read refresh from cookie, rotate, return new access."""

    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        refresh = request.COOKIES.get(settings.REFRESH_COOKIE_NAME)
        if not refresh:
            return Response(
                {"detail": "No refresh cookie."}, status=status.HTTP_401_UNAUTHORIZED
            )
        # Feed the cookie value into the serializer.
        request.data["refresh"] = refresh
        try:
            response = super().post(request, *args, **kwargs)
        except (InvalidToken, TokenError):
            resp = Response(
                {"detail": "Invalid refresh token."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            _clear_refresh_cookie(resp)
            return resp
        new_refresh = response.data.pop("refresh", None)
        if new_refresh:
            _set_refresh_cookie(response, new_refresh)
        return response


class LogoutView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(request=None, responses={205: OpenApiResponse(description="Logged out")})
    def post(self, request, *args, **kwargs):
        refresh = request.COOKIES.get(settings.REFRESH_COOKIE_NAME)
        if refresh:
            try:
                RefreshToken(refresh).blacklist()
            except (InvalidToken, TokenError):
                pass
        response = Response(status=status.HTTP_205_RESET_CONTENT)
        _clear_refresh_cookie(response)
        return response


class WsTicketView(APIView):
    """Mint a short-lived, single-use ticket for the audio WebSocket.

    Listening requires an account: narration costs real TTS spend, and progress
    and bookmarks are per-user. Reading a public book needs no account -- that
    path is served by the REST endpoints, not this ticket.
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=None,
        responses=inline_serializer(
            name="WsTicket",
            fields={
                "ticket": serializers.CharField(),
                "expires_in": serializers.IntegerField(),
            },
        ),
    )
    def post(self, request, *args, **kwargs):
        return Response({
            "ticket": make_ws_ticket(request.user),
            "expires_in": settings.WS_TICKET_TTL_SECONDS,
        })


class ProfileView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user
