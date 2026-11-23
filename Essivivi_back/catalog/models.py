from django.conf import settings
from django.db import models
from django.db.models import Q


class Drink(models.Model):
    class DrinkType(models.TextChoices):
        EAU = "eau", "Eau"
        JUS = "jus", "Jus"
        SODA = "soda", "Soda"
        BIERE = "biere", "Bière"
        ENERGISANTE = "boisson_energisante", "Boisson énergisante"
        AUTRE = "autre", "Autre"

    name = models.CharField(max_length=255)
    drink_type = models.CharField(max_length=30, choices=DrinkType.choices, default=DrinkType.AUTRE)
    description = models.TextField(blank=True, default="")
    price = models.DecimalField(max_digits=12, decimal_places=2)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "drink"
        constraints = [
            models.CheckConstraint(condition=Q(price__gte=0), name="drink_price_ck"),
            models.CheckConstraint(
                condition=Q(drink_type__in=["eau", "jus", "soda", "biere", "boisson_energisante", "autre"]),
                name="drink_type_ck",
            ),
        ]

    def __str__(self):
        return self.name


class Stock(models.Model):
    """Stock central : une ligne par boisson."""
    drink = models.OneToOneField(Drink, on_delete=models.PROTECT, primary_key=True, related_name="stock")
    quantity = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "stock"
        constraints = [
            # cohérence (ACID) : jamais de stock négatif, même en cas de bug dans le code
            models.CheckConstraint(condition=Q(quantity__gte=0), name="stock_non_negative_ck"),
        ]


class StockMovement(models.Model):
    """Traçabilité de chaque variation du stock."""

    class Reason(models.TextChoices):
        REAPPRO = "reappro", "Réapprovisionnement"
        VENTE_DIRECTE = "vente_directe", "Vente directe"
        COMMANDE = "commande", "Commande"
        REMISE_EXPIRATION = "remise_expiration", "Remise en stock (commande expirée)"
        AJUSTEMENT = "ajustement", "Ajustement"

    drink = models.ForeignKey(Drink, on_delete=models.PROTECT, related_name="movements")
    delta = models.IntegerField()
    reason = models.CharField(max_length=30, choices=Reason.choices)
    sale = models.ForeignKey("sales.Sale", on_delete=models.PROTECT, null=True, blank=True, related_name="stock_movements")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "stock_movement"
        indexes = [models.Index(fields=["drink", "-created_at"], name="stock_movement_drink_idx")]
        constraints = [
            models.CheckConstraint(condition=~Q(delta=0), name="stock_movement_delta_ck"),
            models.CheckConstraint(
                condition=Q(reason__in=["reappro", "vente_directe", "commande", "remise_expiration", "ajustement"]),
                name="stock_movement_reason_ck",
            ),
        ]
