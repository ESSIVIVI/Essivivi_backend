from django.db import transaction
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import HasPermission

from .models import Drink, Stock, StockMovement
from .serializers import (
    DrinkCreateSerializer,
    DrinkSerializer,
    DrinkUpdateSerializer,
    RestockSerializer,
    StockAdjustSerializer,
    StockMovementSerializer,
    StockSerializer,
)


# ---------------------------------------------------------------------------
# Boissons
# ---------------------------------------------------------------------------
class DrinkListCreateView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]

    def get_required_permission(self):
        return "drinks.manage" if self.request.method == "POST" else "drinks.view"

    @property
    def required_permission(self):
        return self.get_required_permission()

    @extend_schema(
        responses=DrinkSerializer(many=True),
        summary="Lister les boissons",
        description="Le client ne voit que les boissons disponibles (is_available=true).",
        parameters=[
            OpenApiParameter("type", str, description="Filtrer par type (eau, jus, soda, biere, boisson_energisante, autre)"),
        ],
    )
    def get(self, request):
        qs = Drink.objects.select_related("stock").order_by("name")
        # Le client ne voit que les boissons disponibles
        if request.user.role.code == "client":
            qs = qs.filter(is_available=True)
        drink_type = request.query_params.get("type")
        if drink_type:
            qs = qs.filter(drink_type=drink_type)
        return Response(DrinkSerializer(qs, many=True).data)

    @extend_schema(
        request=DrinkCreateSerializer,
        responses={201: DrinkSerializer},
        summary="Créer une boisson",
        description="Crée la boisson et initialise son stock.",
    )
    def post(self, request):
        serializer = DrinkCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        initial_quantity = data.pop("initial_quantity", 0)

        with transaction.atomic():
            drink = Drink.objects.create(**data)
            Stock.objects.create(drink=drink, quantity=initial_quantity)
            if initial_quantity > 0:
                StockMovement.objects.create(
                    drink=drink,
                    delta=initial_quantity,
                    reason=StockMovement.Reason.REAPPRO,
                    created_by=request.user,
                )

        drink.refresh_from_db()
        return Response(DrinkSerializer(drink).data, status=status.HTTP_201_CREATED)


class DrinkDetailView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "drinks.view"

    def _get_drink(self, pk):
        try:
            return Drink.objects.select_related("stock").get(pk=pk)
        except Drink.DoesNotExist:
            return None

    @extend_schema(responses=DrinkSerializer, summary="Détail d'une boisson")
    def get(self, request, pk):
        drink = self._get_drink(pk)
        if not drink:
            return Response({"detail": "Boisson introuvable."}, status=status.HTTP_404_NOT_FOUND)
        return Response(DrinkSerializer(drink).data)

    @extend_schema(request=DrinkUpdateSerializer, responses=DrinkSerializer, summary="Modifier une boisson")
    def patch(self, request, pk):
        if not request.user.has_permission("drinks.manage"):
            return Response({"detail": "Permission refusée."}, status=status.HTTP_403_FORBIDDEN)
        drink = self._get_drink(pk)
        if not drink:
            return Response({"detail": "Boisson introuvable."}, status=status.HTTP_404_NOT_FOUND)
        serializer = DrinkUpdateSerializer(drink, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        drink.refresh_from_db()
        return Response(DrinkSerializer(drink).data)


class DrinkDeactivateView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "drinks.manage"

    @extend_schema(responses={200: DrinkSerializer}, summary="Désactiver une boisson")
    def post(self, request, pk):
        try:
            drink = Drink.objects.select_related("stock").get(pk=pk)
        except Drink.DoesNotExist:
            return Response({"detail": "Boisson introuvable."}, status=status.HTTP_404_NOT_FOUND)
        drink.is_available = False
        drink.save(update_fields=["is_available"])
        return Response(DrinkSerializer(drink).data)


# ---------------------------------------------------------------------------
# Stock
# ---------------------------------------------------------------------------
class StockListView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "stock.view"

    @extend_schema(
        responses=StockSerializer(many=True),
        summary="Consulter le stock",
        parameters=[
            OpenApiParameter("low_stock", bool, description="true pour n'afficher que les boissons avec stock < 10"),
        ],
    )
    def get(self, request):
        qs = Stock.objects.select_related("drink").order_by("drink__name")
        if request.query_params.get("low_stock") == "true":
            qs = qs.filter(quantity__lt=10)
        return Response(StockSerializer(qs, many=True).data)


class StockRestockView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "stock.restock"

    @extend_schema(
        request=RestockSerializer,
        responses={200: StockSerializer},
        summary="Réapprovisionner le stock",
        description="Ajoute une quantité au stock de la boisson et crée un mouvement de stock.",
    )
    def post(self, request):
        serializer = RestockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            stock = Stock.objects.select_for_update().get(drink_id=data["drink_id"])
            stock.quantity += data["quantity"]
            stock.save(update_fields=["quantity", "updated_at"])
            StockMovement.objects.create(
                drink_id=data["drink_id"],
                delta=data["quantity"],
                reason=StockMovement.Reason.REAPPRO,
                created_by=request.user,
            )

        stock.refresh_from_db()
        return Response(StockSerializer(stock).data)


class StockAdjustView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "stock.restock"

    @extend_schema(
        request=StockAdjustSerializer,
        responses={200: StockSerializer},
        summary="Ajuster le stock",
        description="Définit la quantité absolue du stock. Crée un mouvement d'ajustement.",
    )
    def post(self, request):
        serializer = StockAdjustSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            stock = Stock.objects.select_for_update().get(drink_id=data["drink_id"])
            old_quantity = stock.quantity
            new_quantity = data["quantity"]
            delta = new_quantity - old_quantity

            if delta == 0:
                return Response(StockSerializer(stock).data)

            stock.quantity = new_quantity
            stock.save(update_fields=["quantity", "updated_at"])
            StockMovement.objects.create(
                drink_id=data["drink_id"],
                delta=delta,
                reason=StockMovement.Reason.AJUSTEMENT,
                created_by=request.user,
            )

        stock.refresh_from_db()
        return Response(StockSerializer(stock).data)


class StockMovementListView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "stock.view"

    @extend_schema(
        responses=StockMovementSerializer(many=True),
        summary="Historique des mouvements de stock",
        parameters=[
            OpenApiParameter("drink_id", int, description="Filtrer par boisson"),
            OpenApiParameter("reason", str, description="Filtrer par motif"),
        ],
    )
    def get(self, request):
        qs = StockMovement.objects.select_related("drink", "created_by").order_by("-created_at")
        drink_id = request.query_params.get("drink_id")
        reason = request.query_params.get("reason")
        if drink_id:
            qs = qs.filter(drink_id=drink_id)
        if reason:
            qs = qs.filter(reason=reason)
        return Response(StockMovementSerializer(qs, many=True).data)
