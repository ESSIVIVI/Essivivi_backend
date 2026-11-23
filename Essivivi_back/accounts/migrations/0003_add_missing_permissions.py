"""Ajout des permissions manquantes par rapport au schéma SQL de référence :
- credit.set_upfront : Définir la part à payer avant livraison (admin + gestionnaire)
"""
from django.db import migrations

NEW_PERMISSIONS = [
    ("credit.set_upfront", "Paiements", "Définir la part à payer avant livraison d'une commande à crédit", ["admin", "gestionnaire"]),
]


def add_permissions(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    Permission = apps.get_model("accounts", "Permission")
    RolePermission = apps.get_model("accounts", "RolePermission")

    for code, domain, description, allowed_roles in NEW_PERMISSIONS:
        permission, created = Permission.objects.get_or_create(
            code=code,
            defaults={"domain": domain, "description": description},
        )
        for role_code in allowed_roles:
            try:
                role = Role.objects.get(code=role_code)
                RolePermission.objects.get_or_create(role=role, permission=permission)
            except Role.DoesNotExist:
                pass


def remove_permissions(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    for code, *_ in NEW_PERMISSIONS:
        Permission.objects.filter(code=code).delete()


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_seed_roles_permissions")]
    operations = [migrations.RunPython(add_permissions, remove_permissions)]
