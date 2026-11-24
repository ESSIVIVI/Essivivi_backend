import secrets

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import BackupCode, Permission, Role, RolePermission, User
from .permissions import HasPermission
from .user_serializers import (
    MatrixSerializer,
    PermissionSerializer,
    RoleAssignSerializer,
    RoleMatrixSerializer,
    ResetPasswordSerializer,
    UserSerializer,
    UserUpdateSerializer,
)


def _get_user(pk):
    try:
        return User.objects.select_related("role").get(pk=pk)
    except User.DoesNotExist:
        return None


# ---------------------------------------------------------------------------
# GET /users
# ---------------------------------------------------------------------------
class UserListView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "users.manage"

    @extend_schema(
        responses=UserSerializer(many=True),
        summary="Lister les utilisateurs",
        parameters=[
            OpenApiParameter("role", str, description="Filtrer par rôle (admin, gestionnaire, agent, client)"),
            OpenApiParameter("is_active", bool, description="Filtrer par statut"),
            OpenApiParameter("search", str, description="Recherche sur nom, prénom ou email"),
        ],
    )
    def get(self, request):
        qs = User.objects.select_related("role").order_by("last_name", "first_name")

        role = request.query_params.get("role")
        if role:
            qs = qs.filter(role__code=role)

        is_active = request.query_params.get("is_active")
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() == "true")

        search = request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(email__icontains=search)
            )

        return Response(UserSerializer(qs, many=True).data)


# ---------------------------------------------------------------------------
# GET/PATCH /users/{id}
# ---------------------------------------------------------------------------
class UserDetailView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "users.manage"

    @extend_schema(responses=UserSerializer, summary="Détail d'un utilisateur")
    def get(self, request, pk):
        user = _get_user(pk)
        if not user:
            return Response({"detail": "Utilisateur introuvable."}, status=status.HTTP_404_NOT_FOUND)
        return Response(UserSerializer(user).data)

    @extend_schema(request=UserUpdateSerializer, responses=UserSerializer, summary="Modifier un utilisateur")
    def patch(self, request, pk):
        user = _get_user(pk)
        if not user:
            return Response({"detail": "Utilisateur introuvable."}, status=status.HTTP_404_NOT_FOUND)
        serializer = UserUpdateSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        user.refresh_from_db()
        return Response(UserSerializer(user).data)


# ---------------------------------------------------------------------------
# POST /users/{id}/deactivate
# ---------------------------------------------------------------------------
class UserDeactivateView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "users.manage"

    @extend_schema(responses=UserSerializer, summary="Désactiver un compte")
    def post(self, request, pk):
        user = _get_user(pk)
        if not user:
            return Response({"detail": "Utilisateur introuvable."}, status=status.HTTP_404_NOT_FOUND)
        if user.pk == request.user.pk:
            return Response({"detail": "Vous ne pouvez pas désactiver votre propre compte."}, status=status.HTTP_400_BAD_REQUEST)
        user.is_active = False
        user.save(update_fields=["is_active"])
        return Response(UserSerializer(user).data)


# ---------------------------------------------------------------------------
# POST /users/{id}/activate
# ---------------------------------------------------------------------------
class UserActivateView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "users.manage"

    @extend_schema(responses=UserSerializer, summary="Réactiver un compte")
    def post(self, request, pk):
        user = _get_user(pk)
        if not user:
            return Response({"detail": "Utilisateur introuvable."}, status=status.HTTP_404_NOT_FOUND)
        user.is_active = True
        user.save(update_fields=["is_active"])
        return Response(UserSerializer(user).data)


# ---------------------------------------------------------------------------
# DELETE /users/{id}
# ---------------------------------------------------------------------------
class UserDeleteView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "users.manage"

    @extend_schema(responses={204: None}, summary="Supprimer un compte")
    def delete(self, request, pk):
        user = _get_user(pk)
        if not user:
            return Response({"detail": "Utilisateur introuvable."}, status=status.HTTP_404_NOT_FOUND)
        if user.pk == request.user.pk:
            return Response({"detail": "Vous ne pouvez pas supprimer votre propre compte."}, status=status.HTTP_400_BAD_REQUEST)
        # Si l'utilisateur a un historique, on refuse la suppression physique
        from sales.models import Sale
        has_history = Sale.objects.filter(agent__user=user).exists() or Sale.objects.filter(client__user=user).exists()
        if has_history:
            return Response(
                {"detail": "Ce compte a un historique. Désactivez-le plutôt que de le supprimer."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# PATCH /users/{id}/role
# ---------------------------------------------------------------------------
class UserRoleView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "users.assign_role"

    @extend_schema(request=RoleAssignSerializer, responses=UserSerializer, summary="Changer le rôle d'un utilisateur")
    def patch(self, request, pk):
        user = _get_user(pk)
        if not user:
            return Response({"detail": "Utilisateur introuvable."}, status=status.HTTP_404_NOT_FOUND)
        if user.pk == request.user.pk:
            return Response({"detail": "Vous ne pouvez pas changer votre propre rôle."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = RoleAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            role = Role.objects.get(code=serializer.validated_data["role"])
        except Role.DoesNotExist:
            return Response({"detail": "Rôle introuvable."}, status=status.HTTP_404_NOT_FOUND)

        user.role = role
        user.save(update_fields=["role"])
        user.refresh_from_db()
        return Response(UserSerializer(user).data)


# ---------------------------------------------------------------------------
# POST /users/{id}/reset-password
# ---------------------------------------------------------------------------
class UserResetPasswordView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "users.reset_credentials"

    @extend_schema(
        request=ResetPasswordSerializer,
        responses={200: {"type": "object"}},
        summary="Réinitialiser le mot de passe d'un utilisateur",
    )
    def post(self, request, pk):
        user = _get_user(pk)
        if not user:
            return Response({"detail": "Utilisateur introuvable."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_password = serializer.validated_data["new_password"]

        try:
            validate_password(new_password, user=user)
        except DjangoValidationError as e:
            return Response({"new_password": e.messages}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save(update_fields=["password"])

        send_mail(
            subject="Votre mot de passe ESSIVIVI a été réinitialisé",
            message=(
                f"Bonjour {user.first_name},\n\n"
                "Votre mot de passe a été réinitialisé par un administrateur.\n"
                "Connectez-vous avec votre nouveau mot de passe et changez-le dès que possible."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
        )

        return Response({"detail": "Mot de passe réinitialisé avec succès."})


# ---------------------------------------------------------------------------
# POST /users/{id}/reset-2fa
# ---------------------------------------------------------------------------
class UserReset2FAView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "users.reset_credentials"

    @extend_schema(responses={200: {"type": "object"}}, summary="Réinitialiser le 2FA d'un utilisateur")
    def post(self, request, pk):
        user = _get_user(pk)
        if not user:
            return Response({"detail": "Utilisateur introuvable."}, status=status.HTTP_404_NOT_FOUND)

        user.two_factor_enabled = False
        user.totp_secret = None
        user.save(update_fields=["two_factor_enabled", "totp_secret"])
        BackupCode.objects.filter(user=user).delete()

        send_mail(
            subject="Votre 2FA ESSIVIVI a été réinitialisé",
            message=(
                f"Bonjour {user.first_name},\n\n"
                "Votre authentification à deux facteurs a été réinitialisée par un administrateur.\n"
                "Reconnectez-vous et activez à nouveau le 2FA depuis votre profil."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
        )

        return Response({"detail": "2FA réinitialisé. L'utilisateur devra le réactiver à sa prochaine connexion."})


# ---------------------------------------------------------------------------
# GET /roles/matrix
# PUT /roles/{role_id}/permissions/{perm_id}   → activer un switch
# DELETE /roles/{role_id}/permissions/{perm_id} → désactiver un switch
# ---------------------------------------------------------------------------
class RolesMatrixView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "permissions.manage"

    @extend_schema(responses=MatrixSerializer, summary="Tableau croisé rôles / permissions")
    def get(self, request):
        permissions = Permission.objects.all().order_by("domain", "code")
        roles = Role.objects.prefetch_related("role_permissions__permission").all()
        data = MatrixSerializer({
            "permissions": permissions,
            "roles": roles,
        })
        return Response(data.data)


class RolePermissionSwitchView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "permissions.manage"

    def _get_objects(self, role_id, perm_id):
        try:
            role = Role.objects.get(pk=role_id)
        except Role.DoesNotExist:
            return None, None, Response({"detail": "Rôle introuvable."}, status=status.HTTP_404_NOT_FOUND)
        try:
            permission = Permission.objects.get(pk=perm_id)
        except Permission.DoesNotExist:
            return None, None, Response({"detail": "Permission introuvable."}, status=status.HTTP_404_NOT_FOUND)
        return role, permission, None

    @extend_schema(responses={200: {"type": "object"}}, summary="Activer un switch (rôle + permission)")
    def put(self, request, role_id, perm_id):
        role, permission, error = self._get_objects(role_id, perm_id)
        if error:
            return error
        _, created = RolePermission.objects.get_or_create(role=role, permission=permission)
        return Response({
            "detail": "Switch activé." if created else "Switch déjà activé.",
            "role": role.code,
            "permission": permission.code,
            "enabled": True,
        })

    @extend_schema(responses={200: {"type": "object"}}, summary="Désactiver un switch (rôle + permission)")
    def delete(self, request, role_id, perm_id):
        role, permission, error = self._get_objects(role_id, perm_id)
        if error:
            return error
        deleted, _ = RolePermission.objects.filter(role=role, permission=permission).delete()
        return Response({
            "detail": "Switch désactivé." if deleted else "Switch déjà désactivé.",
            "role": role.code,
            "permission": permission.code,
            "enabled": False,
        })
