from rest_framework import generics, permissions
from rest_framework_simplejwt.views import TokenObtainPairView
from django.views.decorators.cache import cache_page
from django.utils.decorators import method_decorator

from django.contrib.auth.models import User
from .serializers import UserSerializer, CustomTokenObtainPairSerializer

# Create your views here.
class RegisterView(generics.CreateAPIView):
    """
    RegisterView is a generic API view for creating new user accounts.

    This view allows any user to register by providing the necessary user details.
    It uses the UserSerializer to validate and save the user data.

    Attributes:
        queryset (QuerySet): A queryset of all User objects.
        serializer_class (Serializer): The serializer class used for validating and saving user data.
        permission_classes (list): A list of permission classes that determine access to this view.
    """
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.AllowAny]



class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


@method_decorator(cache_page(60 * 15), name='dispatch')
class ProfileView(generics.RetrieveUpdateDestroyAPIView):
    """
    ProfileView is a view for retrieving, updating, and deleting the profile of the currently authenticated user.

    Attributes:
        serializer_class (UserSerializer): The serializer class used for validating and deserializing input, and for serializing output.

    Methods:
        get_object(self):
            Returns the currently authenticated user.
    """
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user
    