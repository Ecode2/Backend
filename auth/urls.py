from django.urls import path

from rest_framework import permissions
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView
)

from .serializers import CustomTokenObtainPairSerializer
from . import views


urlpatterns = [
    path("register/", views.RegisterView.as_view(), name="register"),
    path("login/", views.CustomTokenObtainPairView.as_view(), name='login'),
    path("profile/", views.ProfileView.as_view(), name="profile"),
    path("login/", TokenObtainPairView.as_view(), name='login'),
    path('token/refresh/', TokenRefreshView.as_view(permission_classes = [permissions.AllowAny]), name='token_refresh'),
    path('token/verify/', TokenVerifyView.as_view(permission_classes = [permissions.AllowAny]), name='token_verify'),
]