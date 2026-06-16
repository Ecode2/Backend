from django.urls import path

from rest_framework_simplejwt.views import TokenVerifyView

from . import views

urlpatterns = [
    path("register/", views.RegisterView.as_view(), name="register"),
    path("login/", views.CustomTokenObtainPairView.as_view(), name="login"),
    path("refresh/", views.CookieTokenRefreshView.as_view(), name="token_refresh"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("ws-ticket/", views.WsTicketView.as_view(), name="ws_ticket"),
    path("profile/", views.ProfileView.as_view(), name="profile"),
    path("token/verify/", TokenVerifyView.as_view(), name="token_verify"),
    # Backward-compatible alias for the old refresh path.
    path("token/refresh/", views.CookieTokenRefreshView.as_view(), name="token_refresh_legacy"),
]
