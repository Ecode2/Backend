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

    def validate_email(self, value):
        value = value.strip().lower()
        qs = User.objects.filter(email__iexact=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate_username(self, value):
        value = value.strip()
        qs = User.objects.filter(username__iexact=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("This username is taken.")
        return value

    def validate(self, attrs):
        # Run Django's configured password rules (length, common, numeric...).
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError

        if "password" not in attrs:  # partial profile update, no password change
            return attrs
        candidate = self.instance or User(
            username=attrs.get("username", ""), email=attrs.get("email", "")
        )
        try:
            validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})
        return attrs

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        instance = super().update(instance, validated_data)
        if password:
            instance.set_password(password)  # never store the raw value
            instance.save(update_fields=["password"])
        return instance

    def create(self, validated_data):
        return get_user_model().objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"],
        )


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # Add custom claims here if needed
        return token

    def validate(self, attrs):
        # One generic message for "no such user" and "wrong password": telling
        # them apart lets anyone probe which emails have accounts. Email is
        # matched case-insensitively and a duplicate can no longer 500.
        identifier = (attrs.get("username") or "").strip()
        user = (
            User.objects.filter(email__iexact=identifier).first()
            or User.objects.filter(username__iexact=identifier).first()
        )
        if user is None or not user.check_password(attrs.get("password", "")):
            raise serializers.ValidationError(
                {"detail": "Incorrect email or password."}
            )

        attrs["username"] = user.username
        data = super().validate(attrs)

        if api_settings.UPDATE_LAST_LOGIN:
            update_last_login(None, user)

        return data
