from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import get_user_model
from django.contrib.auth.models import update_last_login
from rest_framework_simplejwt.settings import api_settings

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    """
    UserSerializer is a ModelSerializer for the django User model
    Fields:
        - id: The unique identifier for the user (read-only).
        - username: The username of the user.
        - email: The email address of the user.
        - password: The password of the user (write-only).
    """
    

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password']
        extra_kwargs = {'password': {'write_only': True}}
        read_only_fields = ['id']

    def create(self, validated_data):
        user = get_user_model().objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"]
        )
        return user
    



class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # Add custom claims here if needed
        return token

    def validate(self, attrs):
        try:
            user = User.objects.get(email=attrs['username'])
        except User.DoesNotExist:
            raise serializers.ValidationError('No user with this email found.')

        if not user.check_password(attrs['password']):
            raise serializers.ValidationError('Incorrect password.')

        # Include default behaviour
        attrs["username"] = user.username
        data = super().validate(attrs)
        
        # Update last login
        if api_settings.UPDATE_LAST_LOGIN:
            update_last_login(None, user)
        
        return data
