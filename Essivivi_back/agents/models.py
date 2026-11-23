from django.conf import settings
from django.db import models
from django.db.models import Q


class Agent(models.Model):
    """Agent commercial / livreur. La clé primaire est le compte utilisateur."""

    class PayMode(models.TextChoices):
        SALAIRE = "salaire", "Salaire mensuel"
        COMMISSION = "commission", "Commission"

    class Availability(models.TextChoices):
        HORS_SERVICE = "hors_service", "Hors service"
        DISPO = "dispo", "Disponible"
        OCCUPE = "occupe", "Occupé"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, primary_key=True, related_name="agent_profile")
    zone = models.CharField(max_length=255, blank=True, default="")
    registered_at = models.DateTimeField(auto_now_add=True)
    # Rémunération : paramétrée uniquement par l'administrateur (historique dans AgentPayHistory)
    pay_mode = models.CharField(max_length=20, choices=PayMode.choices)
    monthly_salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)  # % du montant vendu
    # Disponibilité et dernière position (suivi des livraisons)
    availability = models.CharField(max_length=20, choices=Availability.choices, default=Availability.HORS_SERVICE)
    last_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    last_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    last_seen = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "agent"
        indexes = [models.Index(fields=["availability"], name="agent_availability_idx")]
        constraints = [
            models.CheckConstraint(condition=Q(pay_mode__in=["salaire", "commission"]), name="agent_pay_mode_ck"),
            models.CheckConstraint(
                condition=(
                    Q(pay_mode="salaire", monthly_salary__isnull=False, monthly_salary__gte=0)
                    | Q(pay_mode="commission", commission_rate__isnull=False, commission_rate__gte=0, commission_rate__lte=100)
                ),
                name="agent_pay_values_ck",
            ),
            models.CheckConstraint(
                condition=Q(availability__in=["hors_service", "dispo", "occupe"]),
                name="agent_availability_ck",
            ),
        ]

    def __str__(self):
        return self.user.get_full_name()


class AgentLocation(models.Model):
    """Historique des positions pendant une livraison."""
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="locations")
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    accuracy_m = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "agent_location"
        indexes = [models.Index(fields=["agent", "-recorded_at"], name="agent_location_idx")]
        constraints = [
            models.CheckConstraint(condition=Q(latitude__gte=-90, latitude__lte=90), name="agent_location_lat_ck"),
            models.CheckConstraint(condition=Q(longitude__gte=-180, longitude__lte=180), name="agent_location_lng_ck"),
        ]


class AgentPayout(models.Model):
    """Rémunération mensuelle (salaire ou commission)."""

    class Status(models.TextChoices):
        A_PAYER = "a_payer", "À payer"
        PAYE = "paye", "Payé"

    agent = models.ForeignKey(Agent, on_delete=models.PROTECT, related_name="payouts")
    period_month = models.DateField()  # 1er jour du mois
    pay_mode = models.CharField(max_length=20, choices=Agent.PayMode.choices)
    sales_base = models.DecimalField(max_digits=12, decimal_places=2, default=0)  # montant vendu des livraisons « livrée » du mois
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.A_PAYER)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "agent_payout"
        constraints = [
            models.UniqueConstraint(fields=["agent", "period_month"], name="agent_payout_period_uniq"),
            models.CheckConstraint(condition=Q(amount__gte=0), name="agent_payout_amount_ck"),
            models.CheckConstraint(condition=Q(pay_mode__in=["salaire", "commission"]), name="agent_payout_mode_ck"),
            models.CheckConstraint(condition=Q(status__in=["a_payer", "paye"]), name="agent_payout_status_ck"),
        ]


class AgentPayHistory(models.Model):
    """Historique de rémunération, consultable par l'administrateur.
    Rempli AUTOMATIQUEMENT par un déclencheur PostgreSQL (migration 0002) :
    ne pas écrire dans cette table depuis le code.
    Avant de modifier la rémunération d'un agent, indiquer l'auteur dans la
    même transaction :  SET LOCAL app.user_id = '<id de l'administrateur>';"""
    agent = models.ForeignKey(Agent, on_delete=models.PROTECT, related_name="pay_history")
    old_pay_mode = models.CharField(max_length=20, null=True, blank=True)
    old_monthly_salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    old_commission_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    new_pay_mode = models.CharField(max_length=20)
    new_monthly_salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    new_commission_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "agent_pay_history"
        indexes = [models.Index(fields=["agent", "-changed_at"], name="agent_pay_history_idx")]
