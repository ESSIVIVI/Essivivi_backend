from rest_framework import serializers

from .models import Drink, Stock, StockMovement


# ---------------------------------------------------------------------------
# Boissons
# ---------------------------------------------------------------------------
class DrinkSerializer(serializers.ModelSerializer):
    stock_quantity = serializers.IntegerField(source="stock.quantity", read_only=True, default=0)

    class Meta:
        model = Drink
        fields = [
            "id", "name", "drink_type", "description",
            "price", "is_available", "stock_quantity", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class DrinkCreateSerializer(serializers.ModelSerializer):
    initial_quantity = serializers.IntegerField(min_value=0, default=0, write_only=True,
                                                help_text="Quantité initiale en stock.")

    class Meta:
        model = Drink
        fields = ["name", "drink_type", "description", "price", "is_available", "initial_quantity"]

    def validate_price(self, value):
        if value < 0:
            raise serializers.ValidationError("Le prix ne peut pas être négatif.")
        return value


class DrinkUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Drink
        fields = ["name", "drink_type", "description", "price", "is_available"]

    def validate_price(self, value):
        if value < 0:
            raise serializers.ValidationError("Le prix ne peut pas être négatif.")
        return value


# ---------------------------------------------------------------------------
# Stock
# ---------------------------------------------------------------------------
class StockSerializer(serializers.ModelSerializer):
    drink_id = serializers.IntegerField(source="drink.id", read_only=True)
    drink_name = serializers.CharField(source="drink.name", read_only=True)
    drink_type = serializers.CharField(source="drink.drink_type", read_only=True)
    price = serializers.DecimalField(source="drink.price", max_digits=12, decimal_places=2, read_only=True)
    is_available = serializers.BooleanField(source="drink.is_available", read_only=True)

    class Meta:
        model = Stock
        fields = ["drink_id", "drink_name", "drink_type", "price", "is_available", "quantity", "updated_at"]


class RestockSerializer(serializers.Serializer):
    drink_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)

    def validate_drink_id(self, value):
        if not Drink.objects.filter(pk=value).exists():
            raise serializers.ValidationError("Boisson introuvable.")
        return value


class StockAdjustSerializer(serializers.Serializer):
    drink_id = serializers.IntegerField()
    quantity = serializers.IntegerField(help_text="Nouvelle quantité absolue (≥ 0).", min_value=0)
    note = serializers.CharField(max_length=500, required=False, allow_blank=True)

    def validate_drink_id(self, value):
        if not Drink.objects.filter(pk=value).exists():
            raise serializers.ValidationError("Boisson introuvable.")
        return value


# ---------------------------------------------------------------------------
# Mouvements de stock
# ---------------------------------------------------------------------------
class StockMovementSerializer(serializers.ModelSerializer):
    drink_name = serializers.CharField(source="drink.name", read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = StockMovement
        fields = [
            "id", "drink", "drink_name", "delta", "reason",
            "sale", "created_by", "created_by_name", "created_at",
        ]

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name()
        return None
