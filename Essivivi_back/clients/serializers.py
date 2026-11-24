from rest_framework import serializers

from accounts.user_serializers import UserSerializer

from .models import Client, DeliveryPoint


# ---------------------------------------------------------------------------
# Points de livraison (utilisé en lecture dans ClientSerializer)
# ---------------------------------------------------------------------------
class DeliveryPointSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryPoint
        fields = [
            "id", "client", "label", "address",
            "latitude", "longitude", "is_default", "created_at",
        ]
        read_only_fields = ["id", "client", "created_at"]


class DeliveryPointCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryPoint
        fields = ["label", "address", "latitude", "longitude", "is_default"]

    def validate_latitude(self, value):
        if not (-90 <= value <= 90):
            raise serializers.ValidationError("La latitude doit être comprise entre -90 et 90.")
        return value

    def validate_longitude(self, value):
        if not (-180 <= value <= 180):
            raise serializers.ValidationError("La longitude doit être comprise entre -180 et 180.")
        return value


class DeliveryPointUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryPoint
        fields = ["label", "address", "latitude", "longitude", "is_default"]

    def validate_latitude(self, value):
        if not (-90 <= value <= 90):
            raise serializers.ValidationError("La latitude doit être comprise entre -90 et 90.")
        return value

    def validate_longitude(self, value):
        if not (-180 <= value <= 180):
            raise serializers.ValidationError("La longitude doit être comprise entre -180 et 180.")
        return value


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------
class ClientSerializer(serializers.ModelSerializer):
    """Lecture complète d'une fiche client."""
    user = UserSerializer(read_only=True)
    delivery_points = DeliveryPointSerializer(many=True, read_only=True)

    class Meta:
        model = Client
        fields = [
            "id", "user", "business_name", "manager_name",
            "establishment_type", "address", "latitude", "longitude",
            "delivery_points", "created_at",
        ]
        read_only_fields = ["id", "user", "created_at"]


class ClientUpdateSerializer(serializers.ModelSerializer):
    """Mise à jour partielle d'une fiche client (gestionnaire / admin)."""

    class Meta:
        model = Client
        fields = [
            "business_name", "manager_name",
            "establishment_type", "address", "latitude", "longitude",
        ]

    def validate_latitude(self, value):
        if value is not None and not (-90 <= value <= 90):
            raise serializers.ValidationError("La latitude doit être comprise entre -90 et 90.")
        return value

    def validate_longitude(self, value):
        if value is not None and not (-180 <= value <= 180):
            raise serializers.ValidationError("La longitude doit être comprise entre -180 et 180.")
        return value
