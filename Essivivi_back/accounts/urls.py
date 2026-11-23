from django.urls import path

from .views import (
    BackupCodeUseView,
    ChangePasswordView,
    ClientRegisterView,
    EmailVerifyView,
    InvitationActivateView,
    InvitationAdminDetailView,
    InvitationCancelView,
    InvitationListCreateView,
    InvitationResendView,
    InvitationSendCodeView,
    InvitationTokenView,
    LoginView,
    LogoutView,
    MeView,
    RefreshView,
    TotpConfirmView,
    TotpDisableView,
    TotpLoginVerifyView,
    TotpSetupView,
)

urlpatterns = [
    # -------------------------------------------------------------------------
    # Auth
    # -------------------------------------------------------------------------
    path("auth/register", ClientRegisterView.as_view(), name="auth-register"),
    path("auth/email/verify", EmailVerifyView.as_view(), name="auth-email-verify"),
    path("auth/login", LoginView.as_view(), name="auth-login"),
    path("auth/refresh", RefreshView.as_view(), name="auth-refresh"),
    path("auth/logout", LogoutView.as_view(), name="auth-logout"),
    path("auth/password/change", ChangePasswordView.as_view(), name="auth-password-change"),

    # 2FA
    path("auth/2fa/setup", TotpSetupView.as_view(), name="auth-2fa-setup"),
    path("auth/2fa/confirm", TotpConfirmView.as_view(), name="auth-2fa-confirm"),
    path("auth/2fa/disable", TotpDisableView.as_view(), name="auth-2fa-disable"),
    path("auth/2fa/verify", TotpLoginVerifyView.as_view(), name="auth-2fa-verify"),
    path("auth/2fa/backup", BackupCodeUseView.as_view(), name="auth-2fa-backup"),

    # Profil
    path("me", MeView.as_view(), name="me"),

    # -------------------------------------------------------------------------
    # Invitations — routes publiques (token dans l'URL)
    # -------------------------------------------------------------------------
    path("invitations/<str:token>", InvitationTokenView.as_view(), name="invitation-token"),
    path("invitations/<str:token>/send-code", InvitationSendCodeView.as_view(), name="invitation-send-code"),
    path("invitations/<str:token>/activate", InvitationActivateView.as_view(), name="invitation-activate"),

    # -------------------------------------------------------------------------
    # Invitations — routes admin (ID dans l'URL)
    # -------------------------------------------------------------------------
    path("invitations", InvitationListCreateView.as_view(), name="invitation-list-create"),
    path("invitations/<int:pk>", InvitationAdminDetailView.as_view(), name="invitation-detail"),
    path("invitations/<int:pk>/resend", InvitationResendView.as_view(), name="invitation-resend"),
    path("invitations/<int:pk>/cancel", InvitationCancelView.as_view(), name="invitation-cancel"),
]
