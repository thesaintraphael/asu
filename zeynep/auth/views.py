import django.core.validators
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext

from rest_framework import permissions, serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from zeynep.auth.models import User
from zeynep.utils.views import ExtendedViewSet
from zeynep.verification.models import (
    PasswordResetVerification,
    RegistrationVerification,
)


class UserPublicReadSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = User
        fields = (
            "id",
            "display_name",
            "username",
            "date_joined",
            "url",
        )
        extra_kwargs = {"url": {"lookup_field": "username"}}


class UserPrivateReadSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "display_name",
            "username",
            "gender",
            "birth_date",
            "date_joined",
            "url",
        )
        extra_kwargs = {"url": {"lookup_field": "username"}}


class UserUpdateSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = User
        fields = (
            "id",
            "display_name",
            "username",
            "gender",
            "birth_date",
            "url",
        )
        extra_kwargs = {"url": {"lookup_field": "username"}}


class UserCreateSerializer(serializers.HyperlinkedModelSerializer):
    consent = serializers.CharField(write_only=True)
    password = serializers.CharField(
        max_length=256,
        write_only=True,
        style={"input_type": "password"},
    )

    def validate_email(self, email):  # noqa
        return User.objects.normalize_email(email)

    @transaction.atomic
    def create(self, validated_data):
        consent = validated_data.pop("consent")
        email = validated_data["email"]

        verification = RegistrationVerification.objects.get_with_consent(
            email, consent
        )

        if verification is None:
            raise serializers.ValidationError(
                {
                    "email": gettext(
                        "This e-mail could not be verified."
                        " Please provide a validated e-mail address."
                    )
                }
            )

        password = validated_data.pop("password")
        user = User(**validated_data)

        try:
            validate_password(password, user=user)
        except django.core.validators.ValidationError as err:
            raise serializers.ValidationError({"password": err.messages})

        user.set_password(password)
        user.save()
        verification.user = user
        verification.date_completed = timezone.now()
        verification.save(update_fields=["user", "date_completed"])
        verification.null_others()
        return user

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "display_name",
            "username",
            "password",
            "gender",
            "birth_date",
            "consent",
            "url",
        )
        extra_kwargs = {"url": {"lookup_field": "username"}}


class PasswordResetSerializer(serializers.Serializer):  # noqa
    email = serializers.EmailField()
    consent = serializers.CharField(write_only=True)
    password = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
    )

    def validate_email(self, email):  # noqa
        return User.objects.normalize_email(email)

    def create(self, validated_data):
        password = validated_data["password"]
        email = validated_data["email"]

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise NotFound

        try:
            validate_password(password, user=user)
        except django.core.validators.ValidationError as err:
            raise serializers.ValidationError({"password": err.messages})

        verification = PasswordResetVerification.objects.get_with_consent(
            email, validated_data["consent"], user=user
        )

        if verification is None:
            raise serializers.ValidationError(
                {"email": gettext("This e-mail could not be verified.")}
            )

        verification.date_completed = timezone.now()
        verification.save(update_fields=["date_completed"])
        verification.null_others()

        user.set_password(password)
        user.save(update_fields=["password"])
        return validated_data


class UserPermissions(permissions.IsAuthenticatedOrReadOnly):
    def has_permission(self, request, view):
        if view.action == "create":
            return True

        return super().has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        has_base_permission = super().has_object_permission(request, view, obj)

        if view.action == "partial_update":
            # Only self-update allowed.
            return (request.user == obj) and has_base_permission

        return has_base_permission


class UserViewSet(ExtendedViewSet):
    mixins = ("list", "retrieve", "create", "update")
    lookup_field = "username"
    http_method_names = ["get", "post", "patch", "head", "options"]
    permission_classes = [UserPermissions]

    def get_queryset(self):
        if self.action == "partial_update":
            return User.objects.active()
        return User.objects.visible()

    def get_serializer_class(self):
        if self.action == "partial_update":
            return UserUpdateSerializer

        if self.action == "create":
            return UserCreateSerializer

        return UserPublicReadSerializer

    @action(
        detail=False,
        methods=["get", "patch"],
        permission_classes=[permissions.IsAuthenticated],
        serializer_class=UserPrivateReadSerializer,
    )
    def me(self, request):
        if request.method == "PATCH":
            detail = reverse(
                "user-detail",
                kwargs={"username": self.request.user.username},
            )
            return HttpResponseRedirect(
                detail, status=status.HTTP_307_TEMPORARY_REDIRECT
            )

        serializer = UserPrivateReadSerializer(
            self.request.user, context=self.get_serializer_context()
        )
        return Response(data=serializer.data, status=status.HTTP_200_OK)

    @action(
        detail=False,
        methods=["post"],
        permission_classes=[permissions.AllowAny],
        serializer_class=PasswordResetSerializer,
        url_path="password-reset",
    )
    def reset_password(self, request):
        return self.get_action_save_response(request, PasswordResetSerializer)
