from rest_framework import serializers

from .models import Permission, Role, RolePermission, User


# ---------------------------------------------------------------------------
# Utilisateurs
# ---------------------------------------------------------------------------
class UserSerializer(serializers.ModelSerializer):
    role_code = serializers.CharField(source="role.code", read_only=True)
    role_name = serializers.CharField(source="role.name", read_only=True)
    full_name = serializers.CharField(source="get_full_name", read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "email", "phone", "first_name", "last_name", "full_name",
            "role_code", "role_name", "is_active", "email_verified",
            "two_factor_enabled", "created_at", "last_login",
        ]


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone", "email"]

    def validate_email(self, value):
        qs = User.objects.filter(email=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Cet email est déjà utilisé.")
        return value

    def validate_phone(self, value):
        if not value:
            return value
        qs = User.objects.filter(phone=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Ce numéro est déjà utilisé.")
        return value


class RoleAssignSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=["admin", "gestionnaire", "agent", "client"])


class ResetPasswordSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, data):
        if data["new_password"] != data["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Les mots de passe ne correspondent pas."})
        return data


# ---------------------------------------------------------------------------
# Matrice rôles / permissions
# ---------------------------------------------------------------------------
class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ["id", "code", "domain", "description"]


class RoleMatrixSerializer(serializers.ModelSerializer):
    """Un rôle avec la liste des permissions activées (codes uniquement)."""
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = ["id", "code", "name", "permissions"]

    def get_permissions(self, obj):
        return list(
            obj.role_permissions.select_related("permission")
            .values_list("permission__code", flat=True)
        )


class MatrixSerializer(serializers.Serializer):
    """Réponse complète : toutes les permissions + tous les rôles avec leurs switchs."""
    permissions = PermissionSerializer(many=True)
    roles = RoleMatrixSerializer(many=True)
