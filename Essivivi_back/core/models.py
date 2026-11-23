from django.conf import settings
from django.db import models


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    type = models.CharField(max_length=50)
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True, default="")
    data = models.JSONField(default=dict, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notification"
        indexes = [models.Index(fields=["user", "-created_at"], name="notification_user_idx")]


class ActivityLog(models.Model):
    """Historique des opérations importantes, consultable par l'administrateur."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    action = models.CharField(max_length=100)  # ex. 'login', 'sale.create', 'delivery.force_validate'
    entity_type = models.CharField(max_length=50, blank=True, default="")
    entity_id = models.BigIntegerField(null=True, blank=True)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "activity_log"
        indexes = [
            models.Index(fields=["user", "-created_at"], name="activity_log_user_idx"),
            models.Index(fields=["action", "-created_at"], name="activity_log_action_idx"),
        ]


class PlatformSetting(models.Model):
    """Paramètres de la plateforme, modifiables par l'administrateur."""
    key = models.CharField(max_length=100, primary_key=True)
    value = models.JSONField()
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "platform_setting"
