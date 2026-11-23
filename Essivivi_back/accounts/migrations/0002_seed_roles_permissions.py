"""Données initiales : rôles, permissions et valeurs par défaut des switchs.

La portée (« siennes », « affectées »…) n'est pas stockée ici : elle est
appliquée par l'API en filtrant les données. L'administrateur peut ensuite
modifier les switchs depuis le tableau croisé.
"""
from django.db import migrations

ROLES = [
    ("admin", "Administrateur"),
    ("gestionnaire", "Gestionnaire"),
    ("agent", "Agent commercial"),
    ("client", "Client"),
]

ALL = ["admin", "gestionnaire", "agent", "client"]

# (code, domaine, description, rôles autorisés par défaut)
PERMISSIONS = [
    ("users.invite", "Utilisateurs", "Inviter / créer un gestionnaire ou un agent", ["admin"]),
    ("users.manage", "Utilisateurs", "Modifier, désactiver ou supprimer un compte", ["admin"]),
    ("users.assign_role", "Utilisateurs", "Attribuer ou modifier un rôle", ["admin"]),
    ("users.reset_credentials", "Utilisateurs", "Réinitialiser un mot de passe ou le 2FA d'un utilisateur", ["admin"]),
    ("permissions.manage", "Utilisateurs", "Gérer la matrice rôles / permissions", ["admin"]),
    ("activity_log.view", "Utilisateurs", "Consulter l'historique des activités", ["admin"]),
    ("settings.manage", "Utilisateurs", "Gérer les paramètres de la plateforme", ["admin"]),
    ("profile.edit_own", "Utilisateurs", "Modifier son profil, son mot de passe et son 2FA", ALL),
    ("agents.manage", "Agents", "Ajouter, modifier, désactiver un agent ; paramétrer sa rémunération et consulter son historique", ["admin"]),
    ("agents.view_performance", "Agents", "Consulter les performances et l'historique d'un agent", ["admin", "gestionnaire", "agent"]),
    ("agents.view_commission", "Agents", "Consulter les commissions / la rémunération", ["admin", "agent"]),
    ("agents.set_service_status", "Agents", "Se mettre en service / hors service", ["agent"]),
    ("drinks.manage", "Boissons", "Ajouter, modifier, désactiver une boisson", ["admin"]),
    ("drinks.view", "Boissons", "Consulter les boissons disponibles", ALL),
    ("stock.view", "Stock", "Consulter le stock", ["admin", "gestionnaire"]),
    ("stock.restock", "Stock", "Réapprovisionner le stock", ["admin", "gestionnaire"]),
    ("clients.manage", "Clients", "Modifier un client", ["admin", "gestionnaire"]),
    ("clients.view", "Clients", "Consulter les clients et leur historique d'achats", ALL),
    ("delivery_points.manage", "Clients", "Gérer les points de livraison d'un client", ["admin", "gestionnaire", "client"]),
    ("clients.map", "Clients", "Consulter la carte des clients", ["admin", "gestionnaire"]),
    ("sales.create_direct", "Ventes", "Enregistrer une vente directe", ["admin", "gestionnaire"]),
    ("sales.view", "Ventes", "Consulter, rechercher et filtrer les ventes", ALL),
    ("payments.record", "Paiements", "Enregistrer et confirmer un paiement intégral", ["admin", "gestionnaire"]),
    ("credit.manage", "Paiements", "Accorder un crédit (part à payer avant livraison, échéance) et enregistrer les versements", ["admin", "gestionnaire"]),
    ("payments.view", "Paiements", "Consulter le suivi des paiements et le reste à payer", ["admin", "gestionnaire", "client"]),
    ("receipts.issue", "Reçus", "Émettre les reçus", ["admin", "gestionnaire"]),
    ("receipts.view", "Reçus", "Consulter les reçus", ["admin", "gestionnaire", "client"]),
    ("orders.create", "Commandes", "Passer une commande", ["client"]),
    ("orders.view", "Commandes", "Consulter une commande et son état", ALL),
    ("deliveries.reassign", "Livraisons", "Réaffecter manuellement une livraison", ["admin", "gestionnaire"]),
    ("deliveries.validate", "Livraisons", "Valider une livraison avec le code", ["agent"]),
    ("deliveries.force_validate", "Livraisons", "Forcer la validation d'une livraison (sensible)", ["admin", "gestionnaire"]),
    ("deliveries.track_agents", "Livraisons", "Suivre la position et le statut des livreurs", ["admin", "gestionnaire"]),
    ("stats.dashboard", "Statistiques", "Consulter le tableau de bord global", ["admin", "gestionnaire"]),
    ("stats.personal", "Statistiques", "Consulter ses statistiques personnelles", ["agent"]),
    ("reports.view", "Statistiques", "Consulter les rapports", ["admin", "gestionnaire"]),
    ("notifications.receive", "Notifications", "Recevoir les notifications qui le concernent", ALL),
]


def seed(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    Permission = apps.get_model("accounts", "Permission")
    RolePermission = apps.get_model("accounts", "RolePermission")

    roles = {code: Role.objects.create(code=code, name=name) for code, name in ROLES}
    for code, domain, description, allowed in PERMISSIONS:
        permission = Permission.objects.create(code=code, domain=domain, description=description)
        RolePermission.objects.bulk_create(
            [RolePermission(role=roles[role_code], permission=permission) for role_code in allowed]
        )


def unseed(apps, schema_editor):
    for model in ("RolePermission", "Permission", "Role"):
        apps.get_model("accounts", model).objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]
    operations = [migrations.RunPython(seed, unseed)]
