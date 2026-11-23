from django.conf import settings
from django.db import models
from django.db.models import Q


def _lat_lng_checks(prefix, nullable):
    lat, lng = Q(latitude__gte=-90, latitude__lte=90), Q(longitude__gte=-180, longitude__lte=180)
    if nullable:
        lat |= Q(latitude__isnull=True)
        lng |= Q(longitude__isnull=True)
    return [
        models.CheckConstraint(condition=lat, name=f"{prefix}_latitude_ck"),
        models.CheckConstraint(condition=lng, name=f"{prefix}_longitude_ck"),
    ]


class Client(models.Model):
    """Fiche client. Le client crée lui-même son compte (avec son téléphone) :
    pas de fiche sans compte, donc `user` est obligatoire."""

    class EstablishmentType(models.TextChoices):
        BAR = "bar", "Bar"
        RESTAURANT = "restaurant", "Restaurant"
        CAFETERIA = "cafeteria", "Cafétéria"
        BOUTIQUE = "boutique", "Boutique"
        AUTRE = "autre", "Autre"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="client_profile")
    business_name = models.CharField(max_length=255)
    manager_name = models.CharField(max_length=255, blank=True, default="")
    establishment_type = models.CharField(max_length=20, choices=EstablishmentType.choices, default=EstablishmentType.AUTRE)
    address = models.CharField(max_length=500, blank=True, default="")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "client"
        constraints = _lat_lng_checks("client", nullable=True) + [
            models.CheckConstraint(
                condition=Q(establishment_type__in=["bar", "restaurant", "cafeteria", "boutique", "autre"]),
                name="client_type_ck",
            ),
        ]

    def __str__(self):
        return self.business_name


class DeliveryPoint(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="delivery_points")
    label = models.CharField(max_length=255)
    address = models.CharField(max_length=500, blank=True, default="")
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "delivery_point"
        constraints = _lat_lng_checks("delivery_point", nullable=False)

    def __str__(self):
        return f"{self.client} — {self.label}"
