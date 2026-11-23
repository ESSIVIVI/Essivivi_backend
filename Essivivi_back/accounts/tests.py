from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from .models import Invitation, Permission, Role, RolePermission, User


def make_user(email, role_code, **extra):
    return User.objects.create_user(
        email=email, password="MotDePasse-Test-123", first_name="Test", last_name=role_code.capitalize(),
        role=Role.objects.get(code=role_code), **extra,
    )


class SeedTests(TestCase):
    def test_quatre_roles(self):
        self.assertEqual(set(Role.objects.values_list("code", flat=True)), {"admin", "gestionnaire", "agent", "client"})

    def test_matrice_par_defaut(self):
        admin, gest = make_user("a@x.com", "admin"), make_user("g@x.com", "gestionnaire")
        agent, client = make_user("ag@x.com", "agent"), make_user("c@x.com", "client")
        self.assertTrue(gest.has_permission("credit.manage"))        # le gestionnaire gère le crédit
        self.assertTrue(admin.has_permission("permissions.manage"))
        self.assertFalse(gest.has_permission("permissions.manage"))
        self.assertTrue(agent.has_permission("deliveries.validate"))
        self.assertFalse(client.has_permission("sales.create_direct"))
        self.assertTrue(client.has_permission("orders.create"))

    def test_switch_modifiable(self):
        gest = make_user("g@x.com", "gestionnaire")
        RolePermission.objects.filter(role=gest.role, permission__code="credit.manage").delete()
        self.assertFalse(gest.has_permission("credit.manage"))

    def test_nombre_de_permissions(self):
        self.assertEqual(Permission.objects.count(), 37)


class UserTests(TestCase):
    def test_2fa_exige_un_secret(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_user("x@x.com", "client", two_factor_enabled=True)

    def test_telephone_unique(self):
        make_user("a@x.com", "client", phone="90000001")
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_user("b@x.com", "client", phone="90000001")

    def test_invitation_trois_essais_maximum(self):
        admin = make_user("a@x.com", "admin")
        invitation = Invitation(
            email="new@x.com", first_name="N", last_name="E", role=Role.objects.get(code="agent"),
            token_hash="h", expires_at=timezone.now(), created_by=admin, code_attempts=4,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            invitation.save()
