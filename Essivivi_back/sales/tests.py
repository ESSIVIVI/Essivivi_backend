from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from accounts.models import Role, User
from agents.models import Agent
from catalog.models import Drink, Stock
from clients.models import Client

from .models import Receipt, Sale


def user(email, role):
    return User.objects.create_user(
        email=email, password="x", first_name="T", last_name=role, role=Role.objects.get(code=role))


class BaseCase(TestCase):
    def setUp(self):
        self.gest = user("g@x.com", "gestionnaire")
        self.client_user = user("c@x.com", "client")
        self.client_obj = Client.objects.create(user=self.client_user, business_name="Bar Ama")
        self.agent = Agent.objects.create(user=user("ag@x.com", "agent"), pay_mode="commission", commission_rate=5)

    def livraison(self, **extra):
        data = dict(type="livraison", status="en_attente", client=self.client_obj, created_by=self.client_user,
                    total=1000, latitude=Decimal("6.13"), longitude=Decimal("1.22"), delivery_code="4821")
        data.update(extra)
        return Sale.objects.create(**data)

    def directe(self, **extra):
        data = dict(type="directe", status="terminee", client=self.client_obj, created_by=self.gest, total=1000, amount_paid=1000)
        data.update(extra)
        return Sale.objects.create(**data)

    def refuse(self, fn):
        with self.assertRaises(IntegrityError), transaction.atomic():
            fn()


class StockTests(TestCase):
    def test_stock_jamais_negatif(self):
        drink = Drink.objects.create(name="Soda 33cl", drink_type="soda", price=500)
        Stock.objects.create(drink=drink, quantity=10)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Stock.objects.filter(drink=drink).update(quantity=-1)


class CreditTests(BaseCase):
    def test_colonnes_calculees(self):
        sale = self.directe(amount_paid=400, credit_granted_by=self.gest, credit_granted_at=timezone.now())
        sale.refresh_from_db()
        self.assertEqual(sale.remaining, Decimal("600.00"))
        self.assertEqual(sale.payment_status, "partiellement_payee")
        self.assertEqual(self.directe().payment_status, "soldee")

    def test_vente_partielle_sans_credit_refusee(self):
        self.refuse(lambda: self.directe(amount_paid=400))

    def test_note_de_credit_sans_credit_refusee(self):
        self.refuse(lambda: self.directe(credit_note="x"))

    def test_vente_directe_sans_agent(self):
        self.refuse(lambda: self.directe(agent=self.agent))

    def test_livraison_sans_code_refusee(self):
        self.refuse(lambda: self.livraison(delivery_code=None))

    def test_commande_payee_sans_paiement_refusee(self):
        order = self.livraison()
        order.status = "payee"
        self.refuse(order.save)

    def test_commande_a_credit_avec_part_reglee(self):
        order = self.livraison(upfront_required=300, amount_paid=300, status="payee",
                               credit_granted_by=self.gest, credit_granted_at=timezone.now())
        self.assertEqual(order.status, "payee")

    def test_commande_a_credit_sans_rien_avant_livraison(self):
        order = self.livraison(upfront_required=0, status="payee",
                               credit_granted_by=self.gest, credit_granted_at=timezone.now())
        order.refresh_from_db()
        self.assertEqual(order.payment_status, "impayee")

    def test_part_avant_livraison_sans_credit_refusee(self):
        self.refuse(lambda: self.livraison(upfront_required=300))

    def test_part_avant_livraison_superieure_au_total_refusee(self):
        self.refuse(lambda: self.livraison(upfront_required=2000, credit_granted_by=self.gest))

    def test_livree_ou_acceptee_exige_un_agent(self):
        self.refuse(lambda: self.livraison(status="acceptee", amount_paid=1000))
        self.livraison(status="acceptee", amount_paid=1000, agent=self.agent)

    def test_trois_essais_de_code_maximum(self):
        self.refuse(lambda: self.livraison(code_attempts=4))


class ReceiptTests(BaseCase):
    def test_numero_de_recu_unique_et_formate(self):
        sale = self.directe()
        first = Receipt.objects.create(type="vente", sale=sale)
        second = Receipt.objects.create(type="vente", sale=sale)
        year = timezone.now().year
        self.assertRegex(first.number, rf"^RC-{year}-\d{{6}}$")
        self.assertNotEqual(first.number, second.number)

    def test_recu_de_paiement_exige_un_paiement(self):
        self.refuse(lambda: Receipt.objects.create(type="paiement", sale=self.directe()))
