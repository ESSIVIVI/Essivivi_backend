from django.contrib.auth import authenticate
from rest_framework import serializers

from .models import Invitation, Role, User


# ---------------------------------------------------------------------------
# Auth : Login
# ---------------------------------------------------------------------------
class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        user = authenticate(
            request=self.context.get("request"),
            email=data["email"],
            password=data["password"],
        )
        if not user:
            raise serializers.ValidationError("Identifiants invalides.")
        if not user.is_active:
            raise serializers.ValidationError("Ce compte est désactivé.")
        data["user"] = user
        return data


# ---------------------------------------------------------------------------
# Profil (/me)
# ---------------------------------------------------------------------------
class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ["code", "name"]


class MeSerializer(serializers.ModelSerializer):
    role = RoleSerializer(read_only=True)
    full_name = serializers.CharField(source="get_full_name", read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "email", "phone", "first_name", "last_name", "full_name",
            "role", "is_active", "email_verified", "two_factor_enabled",
            "created_at", "last_login",
        ]


class MeUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone"]

    def validate_phone(self, value):
        qs = User.objects.filter(phone=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Ce numéro est déjà utilisé.")
        return value


# ---------------------------------------------------------------------------
# Changement de mot de passe
# ---------------------------------------------------------------------------
class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    def validate_current_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Mot de passe actuel incorrect.")
        return value

    def validate(self, data):
        if data["new_password"] != data["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Les mots de passe ne correspondent pas."})
        return data


# ---------------------------------------------------------------------------
# 2FA TOTP
# ---------------------------------------------------------------------------
class TotpVerifySerializer(serializers.Serializer):
    code = serializers.CharField(min_length=6, max_length=6)


class TotpLoginSerializer(serializers.Serializer):
    """Deuxième étape du login quand 2FA est activé."""
    email = serializers.EmailField()
    totp_code = serializers.CharField(min_length=6, max_length=6)


class BackupCodeUseSerializer(serializers.Serializer):
    email = serializers.EmailField()
    backup_code = serializers.CharField(min_length=8, max_length=12)


# ---------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------
class InvitationCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    role = serializers.ChoiceField(choices=["gestionnaire", "agent"])

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Un compte avec cet email existe déjà.")
        if Invitation.objects.filter(email=value, status=Invitation.Status.EN_ATTENTE).exists():
            raise serializers.ValidationError("Une invitation en attente existe déjà pour cet email.")
        return value


class InvitationSerializer(serializers.ModelSerializer):
    role = serializers.SlugRelatedField(slug_field="code", read_only=True)
    created_by = serializers.StringRelatedField()

    class Meta:
        model = Invitation
        fields = [
            "id", "email", "first_name", "last_name", "role",
            "status", "expires_at", "created_by", "created_at", "activated_at",
        ]


class InvitationActivateSerializer(serializers.Serializer):
    """Étape 2 : code + mot de passe → création du compte."""
    code = serializers.CharField(min_length=6, max_length=6)
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, data):
        if data["password"] != data["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Les mots de passe ne correspondent pas."})
        return data


# ---------------------------------------------------------------------------
# Inscription client
# ---------------------------------------------------------------------------
class ClientRegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=30)
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    business_name = serializers.CharField(max_length=255)
    establishment_type = serializers.ChoiceField(
        choices=["bar", "restaurant", "cafeteria", "boutique", "autre"],
        default="autre",
    )

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Un compte avec cet email existe déjà.")
        return value

    def validate_phone(self, value):
        if User.objects.filter(phone=value).exists():
            raise serializers.ValidationError("Ce numéro de téléphone est déjà utilisé.")
        return value

    def validate(self, data):
        if data["password"] != data["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Les mots de passe ne correspondent pas."})
        return data


# ---------------------------------------------------------------------------
# Vérification email client
# ---------------------------------------------------------------------------
class EmailVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(min_length=6, max_length=6)
