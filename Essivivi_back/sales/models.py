from django.conf import settings
from django.db import connection, models
from django.db.models import Case, F, Q, Value, When
from django.db.models.functions import Coalesce


class Sale(models.Model):
    """Vente directe ou livraison (commande d'un client).

    - type « directe »   : client présent à l'entreprise, saisie par le gestionnaire ;
    - type « livraison » : commande du client, livrée par un agent.
    """

    class Type(models.TextChoices):
        DIRECTE = "directe", "Vente directe"
        LIVRAISON = "livraison", "Livraison"

    class Status(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente de paiement"
        PAYEE = "payee", "Payée"
        ACCEPTEE = "acceptee", "Acceptée (livreur attribué)"
        LIVREE = "livree", "Livrée"
        ANNULEE = "annulee", "Annulée"
        TERMINEE = "terminee", "Terminée (vente directe)"

    type = models.CharField(max_length=20, choices=Type.choices)
    status = models.CharField(max_length=20, choices=Status.choices)
    client = models.ForeignKey("clients.Client", on_delete=models.PROTECT, related_name="sales")
    agent = models.ForeignKey("agents.Agent", on_delete=models.PROTECT, null=True, blank=True, related_name="sales")  # livraisons uniquement
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")  # gestionnaire (directe) ou client (livraison)
    delivery_point = models.ForeignKey("clients.DeliveryPoint", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    delivery_address = models.CharField(max_length=500, blank=True, default="")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)  # copie du point de livraison
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    remaining = models.GeneratedField(
        expression=F("total") - F("amount_paid"),
        output_field=models.DecimalField(max_digits=12, decimal_places=2),
        db_persist=True,
    )
    payment_status = models.GeneratedField(
        expression=Case(
            When(amount_paid=0, then=Value("impayee")),
            When(amount_paid__lt=F("total"), then=Value("partiellement_payee")),
            default=Value("soldee"),
        ),
        output_field=models.CharField(max_length=30),
        db_persist=True,
    )

    delivery_code = models.CharField(max_length=10, null=True, blank=True)  # code de livraison (4 à 6 chiffres)
    code_attempts = models.SmallIntegerField(default=0)

    # Crédit : accordé par le gestionnaire (ou l'administrateur) selon l'accord conclu avec le client
    credit_granted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    credit_granted_at = models.DateTimeField(null=True, blank=True)
    credit_note = models.TextField(null=True, blank=True)  # modalités convenues (texte libre)
    credit_due_date = models.DateField(null=True, blank=True)  # échéance éventuelle
    # Commande à crédit : part à payer AVANT la livraison, convenue avec le client (0 = rien)
    upfront_required = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)  # NULL = paiement intégral requis
    upfront_set_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+")

    forced_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+")  # validation forcée
    expires_at = models.DateTimeField(null=True, blank=True)  # commande non payée : annulée après 24 h
    assigned_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sale"
        indexes = [
            models.Index(fields=["-created_at"], name="sale_created_idx"),
            models.Index(fields=["status"], name="sale_status_idx"),
            # file d'attente d'attribution : commandes payées sans livreur
            models.Index(
                fields=["created_at"], name="sale_queue_idx",
                condition=Q(type="livraison", status="payee", agent__isnull=True),
            ),
            # tâche d'expiration : commandes en attente de paiement
            models.Index(fields=["expires_at"], name="sale_expiry_idx", condition=Q(status="en_attente")),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(type="directe", status="terminee")
                    | Q(type="livraison", status__in=["en_attente", "payee", "acceptee", "livree", "annulee"])
                ),
                name="sale_type_status_ck",
            ),
            models.CheckConstraint(condition=~Q(type="directe") | Q(agent__isnull=True), name="sale_direct_no_agent_ck"),
            models.CheckConstraint(
                condition=~Q(type="livraison") | Q(delivery_code__isnull=False, latitude__isnull=False, longitude__isnull=False),
                name="sale_delivery_fields_ck",
            ),
            models.CheckConstraint(
                condition=~Q(status__in=["acceptee", "livree"]) | Q(agent__isnull=False),
                name="sale_agent_assigned_ck",
            ),
            # Sans crédit accordé, une vente doit être payée en totalité :
            # seule une commande en attente de paiement (ou annulée) peut être non soldée.
            models.CheckConstraint(
                condition=Q(amount_paid=F("total")) | Q(credit_granted_by__isnull=False) | Q(status__in=["en_attente", "annulee"]),
                name="sale_credit_ck",
            ),
            models.CheckConstraint(
                condition=Q(credit_granted_by__isnull=False)
                | Q(credit_granted_at__isnull=True, credit_note__isnull=True, credit_due_date__isnull=True),
                name="sale_credit_fields_ck",
            ),
            models.CheckConstraint(
                condition=Q(upfront_required__isnull=True) | Q(upfront_required__gte=0, upfront_required__lte=F("total")),
                name="sale_upfront_range_ck",
            ),
            models.CheckConstraint(
                condition=Q(upfront_required__isnull=True) | Q(upfront_required=F("total")) | Q(credit_granted_by__isnull=False),
                name="sale_upfront_credit_ck",
            ),
            # une livraison ne peut passer à « payée » (puis acceptée, livrée) que si la part exigée avant livraison est réglée
            models.CheckConstraint(
                condition=(
                    ~Q(type="livraison")
                    | ~Q(status__in=["payee", "acceptee", "livree"])
                    | Q(amount_paid__gte=Coalesce(F("upfront_required"), F("total")))
                ),
                name="sale_upfront_paid_ck",
            ),
            models.CheckConstraint(condition=Q(total__gte=0), name="sale_total_ck"),
            models.CheckConstraint(condition=Q(amount_paid__gte=0, amount_paid__lte=F("total")), name="sale_paid_le_total_ck"),
            models.CheckConstraint(condition=Q(code_attempts__gte=0, code_attempts__lte=3), name="sale_code_attempts_ck"),  # 3 essais maximum
            models.CheckConstraint(
                condition=Q(latitude__isnull=True) | Q(latitude__gte=-90, latitude__lte=90), name="sale_latitude_ck"),
            models.CheckConstraint(
                condition=Q(longitude__isnull=True) | Q(longitude__gte=-180, longitude__lte=180), name="sale_longitude_ck"),
        ]

    def __str__(self):
        return f"Vente #{self.pk} ({self.type}, {self.status})"


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    drink = models.ForeignKey("catalog.Drink", on_delete=models.PROTECT, related_name="+")
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)  # prix copié au moment de la vente
    line_total = models.GeneratedField(
        expression=F("quantity") * F("unit_price"),
        output_field=models.DecimalField(max_digits=12, decimal_places=2),
        db_persist=True,
    )

    class Meta:
        db_table = "sale_item"
        constraints = [
            models.UniqueConstraint(fields=["sale", "drink"], name="sale_item_uniq"),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="sale_item_quantity_ck"),
            models.CheckConstraint(condition=Q(unit_price__gte=0), name="sale_item_price_ck"),
        ]


class Payment(models.Model):
    """Un versement ; plusieurs par vente en cas de crédit.
    À la confirmation, l'application met à jour Sale.amount_paid dans la même
    transaction (select_for_update sur la vente).
    Un versement qui ne solde pas la vente exige la permission credit.manage."""

    class Method(models.TextChoices):
        ESPECES = "especes", "Espèces"
        MOBILE_MONEY = "mobile_money", "Mobile Money"

    class Status(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente"
        CONFIRME = "confirme", "Confirmé"
        REJETE = "rejete", "Rejeté"

    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=20, choices=Method.choices)
    reference = models.CharField(max_length=255, blank=True, default="")  # référence de transaction saisie par le client
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.EN_ATTENTE)
    declared_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "payment"
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="payment_amount_ck"),
            models.CheckConstraint(condition=Q(method__in=["especes", "mobile_money"]), name="payment_method_ck"),
            models.CheckConstraint(condition=Q(status__in=["en_attente", "confirme", "rejete"]), name="payment_status_ck"),
            models.CheckConstraint(
                condition=~Q(status="confirme") | Q(confirmed_by__isnull=False, confirmed_at__isnull=False),
                name="payment_confirmed_ck",
            ),
        ]


class Receipt(models.Model):
    class Type(models.TextChoices):  # liste à confirmer (section 10.8 du cahier)
        VENTE = "vente", "Reçu de vente"
        PAIEMENT = "paiement", "Reçu de paiement"
        BON_LIVRAISON = "bon_livraison", "Bon de livraison"

    number = models.CharField(max_length=30, unique=True, editable=False)
    type = models.CharField(max_length=20, choices=Type.choices)
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name="receipts")
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, null=True, blank=True, related_name="receipts")
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    issued_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "receipt"
        constraints = [
            models.CheckConstraint(condition=Q(type__in=["vente", "paiement", "bon_livraison"]), name="receipt_type_ck"),
            models.CheckConstraint(condition=~Q(type="paiement") | Q(payment__isnull=False), name="receipt_payment_ck"),
        ]

    def save(self, *args, **kwargs):
        if not self.number:
            # séquence PostgreSQL créée par la migration sales.0002 : numéro unique sans doublon, même en concurrence
            with connection.cursor() as cursor:
                cursor.execute("SELECT 'RC-' || to_char(now(), 'YYYY') || '-' || lpad(nextval('receipt_number_seq')::text, 6, '0')")
                self.number = cursor.fetchone()[0]
        super().save(*args, **kwargs)
