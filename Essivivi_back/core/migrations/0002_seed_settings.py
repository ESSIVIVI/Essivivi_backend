"""Paramètres de la plateforme par défaut (modifiables par l'administrateur)."""
from django.db import migrations

SETTINGS = {
    "order_expiry_hours": 24,          # commande non payée : annulée après 24 h
    "delivery_radius_m": 100,          # rayon de validation d'une livraison
    "code_max_attempts": 3,            # essais maximum pour un code
    "agent_location_max_age_s": 120,   # position de moins de 2 min pour être candidat à une livraison
    "location_ping_interval_s": 10,    # envoi de position par l'application de l'agent
    "invitation_ttl_hours": 48,
}


def seed(apps, schema_editor):
    PlatformSetting = apps.get_model("core", "PlatformSetting")
    for key, value in SETTINGS.items():
        PlatformSetting.objects.create(key=key, value=value)


def unseed(apps, schema_editor):
    apps.get_model("core", "PlatformSetting").objects.filter(key__in=SETTINGS).delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]
    operations = [migrations.RunPython(seed, unseed)]
