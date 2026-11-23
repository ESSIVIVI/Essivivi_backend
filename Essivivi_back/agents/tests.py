from django.db import connection, transaction
from django.test import TestCase

from accounts.models import Role, User

from .models import Agent, AgentPayHistory


class PayHistoryTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="a@x.com", password="x", first_name="A", last_name="D", role=Role.objects.get(code="admin"))
        user = User.objects.create_user(
            email="ag@x.com", password="x", first_name="A", last_name="G", role=Role.objects.get(code="agent"))
        self.agent = Agent.objects.create(user=user, pay_mode="commission", commission_rate=5)

    def test_creation_consignee(self):
        self.assertEqual(AgentPayHistory.objects.filter(agent=self.agent).count(), 1)

    def test_modification_consignee_avec_auteur(self):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('app.user_id', %s, true)", [str(self.admin.pk)])  # = SET LOCAL
            Agent.objects.filter(pk=self.agent.pk).update(pay_mode="salaire", monthly_salary=150000, commission_rate=None)
        last = AgentPayHistory.objects.filter(agent=self.agent).latest("id")
        self.assertEqual((last.old_pay_mode, last.new_pay_mode), ("commission", "salaire"))
        self.assertEqual(last.changed_by_id, self.admin.pk)

    def test_changement_de_zone_non_consigne(self):
        Agent.objects.filter(pk=self.agent.pk).update(zone="Lomé nord")
        self.assertEqual(AgentPayHistory.objects.filter(agent=self.agent).count(), 1)
