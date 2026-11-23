import hashlib
import secrets

import pyotp
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .models import BackupCode, Invitation, Role, User
from .permissions import HasPermission
from .serializers import (
    BackupCodeUseSerializer,
    ChangePasswordSerializer,
    ClientRegisterSerializer,
    EmailVerifySerializer,
    InvitationActivateSerializer,
    InvitationCreateSerializer,
    InvitationSerializer,
    LoginSerializer,
    MeSerializer,
    MeUpdateSerializer,
    TotpLoginSerializer,
    TotpVerifySerializer,
)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _issue_tokens(user):
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


def _user_payload(user):
    return {
        "id": user.pk,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "role": user.role.code,
        "two_factor_enabled": user.two_factor_enabled,
    }


# ---------------------------------------------------------------------------
# Auth : Login / Refresh / Logout
# ---------------------------------------------------------------------------
class LoginView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request=LoginSerializer,
        responses={200: {"type": "object"}},
        summary="Connexion",
        description=(
            "Retourne les tokens si le 2FA est désactivé. "
            "Si `two_factor_required: true`, appeler POST /auth/2fa/verify."
        ),
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        if user.two_factor_enabled:
            return Response({"two_factor_required": True, "email": user.email})

        tokens = _issue_tokens(user)
        return Response({**tokens, "user": _user_payload(user)})


class RefreshView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request={"type": "object", "properties": {"refresh": {"type": "string"}}},
        responses={200: {"type": "object"}},
        summary="Rafraîchir le token",
    )
    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response({"detail": "Le champ 'refresh' est requis."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            refresh = RefreshToken(refresh_token)
            return Response({"access": str(refresh.access_token)})
        except TokenError as e:
            return Response({"detail": str(e)}, status=status.HTTP_401_UNAUTHORIZED)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request={"type": "object", "properties": {"refresh": {"type": "string"}}},
        responses={204: None},
        summary="Déconnexion",
    )
    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response({"detail": "Le champ 'refresh' est requis."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            RefreshToken(refresh_token).blacklist()
        except TokenError:
            pass
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Inscription client + vérification email
# ---------------------------------------------------------------------------
class ClientRegisterView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request=ClientRegisterSerializer,
        responses={201: {"type": "object"}},
        summary="Inscription client",
        description="Crée un compte client + sa fiche Client. Envoie un code de vérification par e-mail.",
    )
    def post(self, request):
        from clients.models import Client

        serializer = ClientRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            validate_password(data["password"])
        except DjangoValidationError as e:
            return Response({"password": e.messages}, status=status.HTTP_400_BAD_REQUEST)

        role = Role.objects.get(code="client")
        user = User.objects.create_user(
            email=data["email"],
            phone=data["phone"],
            password=data["password"],
            first_name=data["first_name"],
            last_name=data["last_name"],
            role=role,
            email_verified=False,
        )

        Client.objects.create(
            user=user,
            business_name=data["business_name"],
            establishment_type=data.get("establishment_type", "autre"),
        )

        # Envoyer code de vérification
        raw_code = str(secrets.randbelow(900000) + 100000)
        user.totp_secret = _hash(raw_code)  # on réutilise totp_secret temporairement
        user.save(update_fields=["totp_secret"])

        send_mail(
            subject="Vérification de votre adresse e-mail ESSIVIVI",
            message=(
                f"Bonjour {user.first_name},\n\n"
                f"Votre code de vérification est : {raw_code}\n"
                "Il est valable 15 minutes."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
        )

        return Response(
            {"detail": "Compte créé. Vérifiez votre e-mail pour activer votre compte.", "email": user.email},
            status=status.HTTP_201_CREATED,
        )


class EmailVerifyView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request=EmailVerifySerializer,
        responses={200: {"type": "object"}},
        summary="Vérification e-mail client",
        description="Code reçu par e-mail après l'inscription, 3 essais maximum.",
    )
    def post(self, request):
        serializer = EmailVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        code = serializer.validated_data["code"]

        try:
            user = User.objects.select_related("role").get(email=email, is_active=True)
        except User.DoesNotExist:
            return Response({"detail": "Compte introuvable."}, status=status.HTTP_404_NOT_FOUND)

        if user.email_verified:
            return Response({"detail": "E-mail déjà vérifié."})

        if not user.totp_secret or _hash(code) != user.totp_secret:
            return Response({"detail": "Code invalide ou expiré."}, status=status.HTTP_400_BAD_REQUEST)

        user.email_verified = True
        user.totp_secret = None
        user.save(update_fields=["email_verified", "totp_secret"])

        tokens = _issue_tokens(user)
        return Response({**tokens, "user": _user_payload(user)})


# ---------------------------------------------------------------------------
# Profil (/me)
# ---------------------------------------------------------------------------
class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=MeSerializer, summary="Mon profil")
    def get(self, request):
        return Response(MeSerializer(request.user).data)

    @extend_schema(request=MeUpdateSerializer, responses=MeSerializer, summary="Modifier mon profil")
    def patch(self, request):
        serializer = MeUpdateSerializer(request.user, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(MeSerializer(request.user).data)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=ChangePasswordSerializer,
        responses={200: {"type": "object"}},
        summary="Changer mon mot de passe",
    )
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        new_password = serializer.validated_data["new_password"]
        try:
            validate_password(new_password, user=request.user)
        except DjangoValidationError as e:
            return Response({"new_password": e.messages}, status=status.HTTP_400_BAD_REQUEST)
        request.user.set_password(new_password)
        request.user.save(update_fields=["password"])
        return Response({"detail": "Mot de passe modifié avec succès."})


# ---------------------------------------------------------------------------
# 2FA TOTP
# ---------------------------------------------------------------------------
class TotpSetupView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: {"type": "object"}}, summary="Initialiser le 2FA")
    def post(self, request):
        user = request.user
        if user.two_factor_enabled:
            return Response({"detail": "Le 2FA est déjà activé."}, status=status.HTTP_400_BAD_REQUEST)
        secret = pyotp.random_base32()
        user.totp_secret = secret
        user.save(update_fields=["totp_secret"])
        uri = pyotp.totp.TOTP(secret).provisioning_uri(name=user.email, issuer_name="ESSIVIVI")
        return Response({"secret": secret, "uri": uri})


class TotpConfirmView(APIView):
    """Confirme le secret → active le 2FA (nommé /confirm selon le contrat)."""
    permission_classes = [IsAuthenticated]

    @extend_schema(request=TotpVerifySerializer, responses={200: {"type": "object"}}, summary="Activer le 2FA")
    def post(self, request):
        user = request.user
        if user.two_factor_enabled:
            return Response({"detail": "Le 2FA est déjà activé."}, status=status.HTTP_400_BAD_REQUEST)
        if not user.totp_secret:
            return Response({"detail": "Appelez d'abord POST /auth/2fa/setup."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = TotpVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(serializer.validated_data["code"], valid_window=1):
            return Response({"detail": "Code invalide."}, status=status.HTTP_400_BAD_REQUEST)

        raw_codes = [secrets.token_hex(5) for _ in range(8)]
        BackupCode.objects.filter(user=user, used_at__isnull=True).delete()
        BackupCode.objects.bulk_create([BackupCode(user=user, code_hash=_hash(c)) for c in raw_codes])

        user.two_factor_enabled = True
        user.save(update_fields=["two_factor_enabled"])

        return Response({"detail": "2FA activé.", "backup_codes": raw_codes})


class TotpDisableView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=TotpVerifySerializer, responses={200: {"type": "object"}}, summary="Désactiver le 2FA")
    def post(self, request):
        user = request.user
        if not user.two_factor_enabled:
            return Response({"detail": "Le 2FA n'est pas activé."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = TotpVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(serializer.validated_data["code"], valid_window=1):
            return Response({"detail": "Code invalide."}, status=status.HTTP_400_BAD_REQUEST)

        user.two_factor_enabled = False
        user.totp_secret = None
        user.save(update_fields=["two_factor_enabled", "totp_secret"])
        BackupCode.objects.filter(user=user).delete()
        return Response({"detail": "2FA désactivé."})


class TotpLoginVerifyView(APIView):
    """POST /auth/2fa/verify — valide le code TOTP ou de secours et délivre les tokens."""
    permission_classes = [AllowAny]

    @extend_schema(request=TotpLoginSerializer, responses={200: {"type": "object"}}, summary="Valider le code 2FA")
    def post(self, request):
        serializer = TotpLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        totp_code = serializer.validated_data["totp_code"]

        try:
            user = User.objects.select_related("role").get(email=email, is_active=True)
        except User.DoesNotExist:
            return Response({"detail": "Identifiants invalides."}, status=status.HTTP_401_UNAUTHORIZED)

        if not user.two_factor_enabled or not user.totp_secret:
            return Response({"detail": "Le 2FA n'est pas activé sur ce compte."}, status=status.HTTP_400_BAD_REQUEST)

        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(totp_code, valid_window=1):
            return Response({"detail": "Code 2FA invalide ou expiré."}, status=status.HTTP_401_UNAUTHORIZED)

        tokens = _issue_tokens(user)
        return Response({**tokens, "user": _user_payload(user)})


class BackupCodeUseView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=BackupCodeUseSerializer, responses={200: {"type": "object"}}, summary="Login avec code de secours")
    def post(self, request):
        serializer = BackupCodeUseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        raw_code = serializer.validated_data["backup_code"]

        try:
            user = User.objects.select_related("role").get(email=email, is_active=True)
        except User.DoesNotExist:
            return Response({"detail": "Identifiants invalides."}, status=status.HTTP_401_UNAUTHORIZED)

        backup = BackupCode.objects.filter(user=user, code_hash=_hash(raw_code), used_at__isnull=True).first()
        if not backup:
            return Response({"detail": "Code de secours invalide ou déjà utilisé."}, status=status.HTTP_401_UNAUTHORIZED)

        backup.used_at = timezone.now()
        backup.save(update_fields=["used_at"])

        tokens = _issue_tokens(user)
        return Response({**tokens, "user": _user_payload(user)})


# ---------------------------------------------------------------------------
# Invitations — conformes au contrat d'API
# GET  /invitations/{token}          → vérifier le lien
# POST /invitations/{token}/send-code → envoyer le code
# POST /invitations/{token}/activate  → créer le compte
# POST /invitations                  → créer une invitation (admin)
# GET  /invitations                  → lister
# POST /invitations/{id}/resend      → renvoyer
# POST /invitations/{id}/cancel      → annuler
# ---------------------------------------------------------------------------
class InvitationListCreateView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "users.invite"

    @extend_schema(responses=InvitationSerializer(many=True), summary="Lister les invitations")
    def get(self, request):
        qs = Invitation.objects.select_related("role", "created_by").order_by("-created_at")
        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return Response(InvitationSerializer(qs, many=True).data)

    @extend_schema(request=InvitationCreateSerializer, responses={201: InvitationSerializer}, summary="Créer une invitation")
    def post(self, request):
        serializer = InvitationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        role = Role.objects.get(code=data["role"])
        raw_token = secrets.token_urlsafe(32)
        ttl = getattr(settings, "INVITATION_TTL_HOURS", 48)

        invitation = Invitation.objects.create(
            email=data["email"],
            first_name=data["first_name"],
            last_name=data["last_name"],
            role=role,
            token_hash=_hash(raw_token),
            expires_at=timezone.now() + timezone.timedelta(hours=ttl),
            created_by=request.user,
        )

        web_url = getattr(settings, "WEB_APP_URL", "http://localhost:5173")
        link = f"{web_url}/invitation/{raw_token}"
        send_mail(
            subject="Votre invitation ESSIVIVI",
            message=(
                f"Bonjour {invitation.first_name},\n\n"
                f"Vous avez été invité(e) à rejoindre ESSIVIVI en tant que {role.name}.\n"
                f"Cliquez sur le lien suivant pour accepter (valable {ttl} h) :\n{link}\n\n"
                "Si vous n'attendiez pas cette invitation, ignorez ce message."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[invitation.email],
        )

        return Response(InvitationSerializer(invitation).data, status=status.HTTP_201_CREATED)


class InvitationTokenView(APIView):
    """GET /invitations/{token} — vérifie la validité du lien sans envoyer de code."""
    permission_classes = [AllowAny]

    @extend_schema(responses={200: {"type": "object"}}, summary="Vérifier un lien d'invitation")
    def get(self, request, token):
        try:
            inv = Invitation.objects.select_related("role").get(token_hash=_hash(token))
        except Invitation.DoesNotExist:
            return Response({"detail": "Lien invalide."}, status=status.HTTP_404_NOT_FOUND)

        if inv.status == Invitation.Status.ACTIVEE:
            return Response({"detail": "Cette invitation a déjà été utilisée."}, status=status.HTTP_400_BAD_REQUEST)
        if inv.status == Invitation.Status.ANNULEE:
            return Response({"detail": "Cette invitation a été annulée."}, status=status.HTTP_400_BAD_REQUEST)
        if inv.status == Invitation.Status.BLOQUEE:
            return Response({"detail": "Cette invitation est bloquée."}, status=status.HTTP_423_LOCKED)
        if timezone.now() > inv.expires_at:
            inv.status = Invitation.Status.EXPIREE
            inv.save(update_fields=["status"])
            return Response({"detail": "Ce lien a expiré."}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "email": inv.email,
            "first_name": inv.first_name,
            "last_name": inv.last_name,
            "role": inv.role.code,
            "expires_at": inv.expires_at,
        })


class InvitationSendCodeView(APIView):
    """POST /invitations/{token}/send-code — envoie le code au clic sur le lien."""
    permission_classes = [AllowAny]

    @extend_schema(responses={200: {"type": "object"}}, summary="Envoyer le code d'activation")
    def post(self, request, token):
        try:
            inv = Invitation.objects.select_related("role").get(token_hash=_hash(token))
        except Invitation.DoesNotExist:
            return Response({"detail": "Lien invalide."}, status=status.HTTP_404_NOT_FOUND)

        if inv.status == Invitation.Status.ACTIVEE:
            return Response({"detail": "Cette invitation a déjà été utilisée."}, status=status.HTTP_400_BAD_REQUEST)
        if inv.status == Invitation.Status.ANNULEE:
            return Response({"detail": "Cette invitation a été annulée."}, status=status.HTTP_400_BAD_REQUEST)
        if inv.status == Invitation.Status.BLOQUEE:
            return Response({"detail": "Cette invitation est bloquée."}, status=status.HTTP_423_LOCKED)
        if timezone.now() > inv.expires_at:
            inv.status = Invitation.Status.EXPIREE
            inv.save(update_fields=["status"])
            return Response({"detail": "Ce lien a expiré."}, status=status.HTTP_400_BAD_REQUEST)

        raw_code = str(secrets.randbelow(900000) + 100000)
        inv.code_hash = _hash(raw_code)
        inv.code_sent_at = timezone.now()
        inv.code_attempts = 0
        inv.save(update_fields=["code_hash", "code_sent_at", "code_attempts"])

        send_mail(
            subject="Votre code d'activation ESSIVIVI",
            message=(
                f"Bonjour {inv.first_name},\n\n"
                f"Votre code d'activation est : {raw_code}\n"
                "Il est valable 15 minutes."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[inv.email],
        )
        return Response({"detail": "Code envoyé par email.", "email": inv.email})


class InvitationActivateView(APIView):
    """POST /invitations/{token}/activate — code + mot de passe → création du compte."""
    permission_classes = [AllowAny]

    @extend_schema(request=InvitationActivateSerializer, responses={201: {"type": "object"}}, summary="Activer l'invitation et créer le compte")
    def post(self, request, token):
        serializer = InvitationActivateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            inv = Invitation.objects.select_related("role").get(token_hash=_hash(token))
        except Invitation.DoesNotExist:
            return Response({"detail": "Lien invalide."}, status=status.HTTP_404_NOT_FOUND)

        if inv.status != Invitation.Status.EN_ATTENTE:
            return Response({"detail": "Cette invitation n'est plus valide."}, status=status.HTTP_400_BAD_REQUEST)
        if timezone.now() > inv.expires_at:
            inv.status = Invitation.Status.EXPIREE
            inv.save(update_fields=["status"])
            return Response({"detail": "Ce lien a expiré."}, status=status.HTTP_400_BAD_REQUEST)
        if not inv.code_hash:
            return Response({"detail": "Appelez d'abord POST /invitations/{token}/send-code."}, status=status.HTTP_400_BAD_REQUEST)
        if inv.code_sent_at and (timezone.now() - inv.code_sent_at).seconds > 900:
            return Response({"detail": "Le code a expiré. Recommencez depuis le lien."}, status=status.HTTP_400_BAD_REQUEST)
        if inv.code_attempts >= 3:
            inv.status = Invitation.Status.BLOQUEE
            inv.save(update_fields=["status"])
            return Response({"detail": "Trop de tentatives. Invitation bloquée."}, status=status.HTTP_423_LOCKED)

        if _hash(data["code"]) != inv.code_hash:
            inv.code_attempts += 1
            inv.save(update_fields=["code_attempts"])
            remaining = 3 - inv.code_attempts
            return Response(
                {"detail": f"Code incorrect. {remaining} tentative(s) restante(s)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            validate_password(data["password"])
        except DjangoValidationError as e:
            return Response({"password": e.messages}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.create_user(
            email=inv.email,
            password=data["password"],
            first_name=inv.first_name,
            last_name=inv.last_name,
            role=inv.role,
            email_verified=True,
        )

        inv.status = Invitation.Status.ACTIVEE
        inv.created_user = user
        inv.activated_at = timezone.now()
        inv.save(update_fields=["status", "created_user", "activated_at"])

        tokens = _issue_tokens(user)
        return Response(
            {**tokens, "user": _user_payload(user)},
            status=status.HTTP_201_CREATED,
        )


class InvitationAdminDetailView(APIView):
    """Actions admin sur une invitation par ID : GET détail, POST renvoyer, POST annuler."""
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "users.invite"

    def _get(self, pk):
        try:
            return Invitation.objects.select_related("role", "created_by").get(pk=pk)
        except Invitation.DoesNotExist:
            return None

    @extend_schema(responses=InvitationSerializer, summary="Détail d'une invitation")
    def get(self, request, pk):
        inv = self._get(pk)
        if not inv:
            return Response({"detail": "Invitation introuvable."}, status=status.HTTP_404_NOT_FOUND)
        return Response(InvitationSerializer(inv).data)


class InvitationResendView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "users.invite"

    @extend_schema(responses={200: InvitationSerializer}, summary="Renvoyer une invitation")
    def post(self, request, pk):
        try:
            inv = Invitation.objects.select_related("role").get(pk=pk)
        except Invitation.DoesNotExist:
            return Response({"detail": "Invitation introuvable."}, status=status.HTTP_404_NOT_FOUND)
        if inv.status == Invitation.Status.ACTIVEE:
            return Response({"detail": "Cette invitation a déjà été activée."}, status=status.HTTP_400_BAD_REQUEST)
        if inv.status == Invitation.Status.ANNULEE:
            return Response({"detail": "Cette invitation a été annulée."}, status=status.HTTP_400_BAD_REQUEST)

        raw_token = secrets.token_urlsafe(32)
        ttl = getattr(settings, "INVITATION_TTL_HOURS", 48)
        inv.token_hash = _hash(raw_token)
        inv.status = Invitation.Status.EN_ATTENTE
        inv.expires_at = timezone.now() + timezone.timedelta(hours=ttl)
        inv.save(update_fields=["token_hash", "status", "expires_at"])

        web_url = getattr(settings, "WEB_APP_URL", "http://localhost:5173")
        link = f"{web_url}/invitation/{raw_token}"
        send_mail(
            subject="Votre invitation ESSIVIVI (renvoi)",
            message=f"Bonjour {inv.first_name},\n\nNouveau lien (valable {ttl} h) :\n{link}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[inv.email],
        )
        return Response(InvitationSerializer(inv).data)


class InvitationCancelView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "users.invite"

    @extend_schema(responses={204: None}, summary="Annuler une invitation")
    def post(self, request, pk):
        try:
            inv = Invitation.objects.get(pk=pk)
        except Invitation.DoesNotExist:
            return Response({"detail": "Invitation introuvable."}, status=status.HTTP_404_NOT_FOUND)
        if inv.status not in (Invitation.Status.EN_ATTENTE, Invitation.Status.EXPIREE):
            return Response(
                {"detail": "Seules les invitations en attente ou expirées peuvent être annulées."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        inv.status = Invitation.Status.ANNULEE
        inv.save(update_fields=["status"])
        return Response(status=status.HTTP_204_NO_CONTENT)
