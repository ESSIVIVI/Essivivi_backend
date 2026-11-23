from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.db.models import Q


# ---------------------------------------------------------------------------
# Rôles et permissions
# Le tableau croisé à switchs de l'admin = la table role_permission :
# une ligne présente = switch activé.
# ---------------------------------------------------------------------------
class Role(models.Model):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)

    class Meta:
        db_table = "role"

    def __str__(self):
        return self.name


class Permission(models.Model):
    code = models.CharField(max_length=100, unique=True)
    domain = models.CharField(max_length=100)
    description = models.CharField(max_length=255)

    class Meta:
        db_table = "permission"
        ordering = ["domain", "code"]

    def __str__(self):
        return self.code


class RolePermission(models.Model):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="role_permissions")
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name="role_permissions")

    class Meta:
        db_table = "role_permission"
        constraints = [
            models.UniqueConstraint(fields=["role", "permission"], name="role_permission_uniq"),
        ]


# ---------------------------------------------------------------------------
# Utilisateurs
# ---------------------------------------------------------------------------
class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create(self, email, password, **extra):
        if not email:
            raise ValueError("L'adresse e-mail est obligatoire.")
        user = self.model(email=self.normalize_email(email), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        """Le rôle (role=...) est obligatoire."""
        return self._create(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("role", Role.objects.get(code="admin"))
        extra.setdefault("email_verified", True)
        return self._create(email, password, **extra)


class User(AbstractBaseUser):
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=30, unique=True, null=True, blank=True)  # obligatoire pour un client (contrôlé par l'API)
    password = models.CharField("password", max_length=128, db_column="password_hash")
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="users")
    is_active = models.BooleanField(default=True)  # « désactiver un compte » ; éviter la suppression physique
    email_verified = models.BooleanField(default=False)
    two_factor_enabled = models.BooleanField(default=False)
    totp_secret = models.TextField(null=True, blank=True)  # à chiffrer côté application
    created_at = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(null=True, blank=True, db_column="last_login_at")

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:
        db_table = "app_user"
        constraints = [
            models.CheckConstraint(
                condition=Q(two_factor_enabled=False) | Q(totp_secret__isnull=False),
                name="user_2fa_secret_ck",
            ),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name} <{self.email}>"

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def role_code(self):
        return self.role.code

    def has_permission(self, code):
        """Vrai si le switch (rôle de l'utilisateur, permission `code`) est activé.
        À mettre en cache plus tard pour ne pas interroger la base à chaque requête."""
        return RolePermission.objects.filter(role_id=self.role_id, permission__code=code).exists()

    # --- Compatibilité avec le site d'administration Django (/admin/) -------
    @property
    def is_staff(self):
        return self.is_active and self.role.code == "admin"

    @property
    def is_superuser(self):
        return self.is_staff

    def has_perm(self, perm, obj=None):
        return self.is_superuser

    def has_module_perms(self, app_label):
        return self.is_superuser


class BackupCode(models.Model):
    """Codes de secours du 2FA, à usage unique."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="backup_codes")
    code_hash = models.CharField(max_length=255)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "backup_code"


class Invitation(models.Model):
    class Status(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente"
        ACTIVEE = "activee", "Activée"
        EXPIREE = "expiree", "Expirée"
        ANNULEE = "annulee", "Annulée"
        BLOQUEE = "bloquee", "Bloquée"

    email = models.EmailField()
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="+")
    token_hash = models.CharField(max_length=255, unique=True)  # le jeton du lien n'est jamais stocké en clair
    code_hash = models.CharField(max_length=255, null=True, blank=True)  # NULL tant que l'employé n'a pas cliqué
    code_sent_at = models.DateTimeField(null=True, blank=True)  # code envoyé AU CLIC sur le lien
    code_attempts = models.SmallIntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.EN_ATTENTE)
    expires_at = models.DateTimeField()
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    created_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    activated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "invitation"
        indexes = [models.Index(fields=["status"], name="invitation_status_idx")]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=["en_attente", "activee", "expiree", "annulee", "bloquee"]),
                name="invitation_status_ck",
            ),
            models.CheckConstraint(
                condition=Q(code_attempts__gte=0, code_attempts__lte=3),  # 3 essais maximum
                name="invitation_attempts_ck",
            ),
        ]


class DeviceToken(models.Model):
    """Jetons Firebase (notifications push)."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="device_tokens")
    token = models.CharField(max_length=512, unique=True)
    platform = models.CharField(max_length=20, default="android")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "device_token"
