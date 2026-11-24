from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import HasPermission

from .models import Client, DeliveryPoint
from .serializers import (
    ClientSerializer,
    ClientUpdateSerializer,
    DeliveryPointCreateSerializer,
    DeliveryPointSerializer,
    DeliveryPointUpdateSerializer,
)


def _get_client(pk):
    try:
        return Client.objects.select_related("user__role").prefetch_related("delivery_points").get(pk=pk)
    except Client.DoesNotExist:
        return None


# ---------------------------------------------------------------------------
# GET  /clients
# ---------------------------------------------------------------------------
class ClientListView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "clients.view"

    @extend_schema(
        responses=ClientSerializer(many=True),
        summary="Lister les clients",
        description=(
            "Administrateur et gestionnaire : tous les clients. "
            "Agent : clients de ses livraisons. "
            "Client : sa propre fiche uniquement."
        ),
        parameters=[
            OpenApiParameter("search", str, description="Recherche sur nom d'établissement, gérant ou e-mail"),
            OpenApiParameter(
                "establishment_type", str,
                description="Filtrer par type (bar, restaurant, cafeteria, boutique, autre)",
            ),
        ],
    )
    def get(self, request):
        role = request.user.role.code

        if role == "client":
            # Le client ne voit que sa propre fiche
            try:
                client = Client.objects.select_related("user__role").prefetch_related(
                    "delivery_points"
                ).get(user=request.user)
                return Response(ClientSerializer([client], many=True).data)
            except Client.DoesNotExist:
                return Response([])

        qs = Client.objects.select_related("user__role").prefetch_related("delivery_points")

        if role == "agent":
            # L'agent ne voit que les clients de ses livraisons
            from sales.models import Sale
            client_ids = Sale.objects.filter(
                agent__user=request.user
            ).values_list("client_id", flat=True).distinct()
            qs = qs.filter(pk__in=client_ids)

        # Filtres communs
        search = request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(business_name__icontains=search)
                | Q(manager_name__icontains=search)
                | Q(user__email__icontains=search)
            )

        establishment_type = request.query_params.get("establishment_type")
        if establishment_type:
            qs = qs.filter(establishment_type=establishment_type)

        qs = qs.order_by("business_name")
        return Response(ClientSerializer(qs, many=True).data)


# ---------------------------------------------------------------------------
# GET  /clients/{id}
# PATCH /clients/{id}
# ---------------------------------------------------------------------------
class ClientDetailView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "clients.view"

    @extend_schema(responses=ClientSerializer, summary="Détail d'un client")
    def get(self, request, pk):
        role = request.user.role.code

        client = _get_client(pk)
        if not client:
            return Response({"detail": "Client introuvable."}, status=status.HTTP_404_NOT_FOUND)

        # Un client ne peut consulter que sa propre fiche
        if role == "client" and client.user_id != request.user.pk:
            return Response({"detail": "Permission refusée."}, status=status.HTTP_403_FORBIDDEN)

        # Un agent ne peut consulter que les clients de ses livraisons
        if role == "agent":
            from sales.models import Sale
            has_delivery = Sale.objects.filter(
                agent__user=request.user, client=client
            ).exists()
            if not has_delivery:
                return Response({"detail": "Permission refusée."}, status=status.HTTP_403_FORBIDDEN)

        return Response(ClientSerializer(client).data)

    @extend_schema(
        request=ClientUpdateSerializer,
        responses=ClientSerializer,
        summary="Modifier une fiche client",
    )
    def patch(self, request, pk):
        if not request.user.has_permission("clients.manage"):
            return Response({"detail": "Permission refusée."}, status=status.HTTP_403_FORBIDDEN)

        client = _get_client(pk)
        if not client:
            return Response({"detail": "Client introuvable."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ClientUpdateSerializer(client, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        client.refresh_from_db()
        return Response(ClientSerializer(client).data)


# ---------------------------------------------------------------------------
# GET /clients/{id}/sales  — historique d'achats d'un client
# ---------------------------------------------------------------------------
class ClientSalesView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "clients.view"

    @extend_schema(
        responses={"200": {"type": "array", "items": {"type": "object"}}},
        summary="Historique des ventes d'un client",
        description=(
            "Retourne toutes les ventes (directes et livraisons) du client. "
            "Un client ne peut consulter que les siennes."
        ),
        parameters=[
            OpenApiParameter("type", str, description="Filtrer par type : directe, livraison"),
            OpenApiParameter("status", str, description="Filtrer par statut"),
            OpenApiParameter("payment_status", str, description="Filtrer par statut de paiement : impayee, partiellement_payee, soldee"),
        ],
    )
    def get(self, request, pk):
        from sales.models import Sale

        client = _get_client(pk)
        if not client:
            return Response({"detail": "Client introuvable."}, status=status.HTTP_404_NOT_FOUND)

        role = request.user.role.code

        # Vérifications de portée
        if role == "client" and client.user_id != request.user.pk:
            return Response({"detail": "Permission refusée."}, status=status.HTTP_403_FORBIDDEN)

        if role == "agent":
            has_delivery = Sale.objects.filter(
                agent__user=request.user, client=client
            ).exists()
            if not has_delivery:
                return Response({"detail": "Permission refusée."}, status=status.HTTP_403_FORBIDDEN)

        qs = Sale.objects.filter(client=client).select_related(
            "agent__user", "created_by", "delivery_point"
        ).order_by("-created_at")

        # Filtres optionnels
        sale_type = request.query_params.get("type")
        if sale_type:
            qs = qs.filter(type=sale_type)

        sale_status = request.query_params.get("status")
        if sale_status:
            qs = qs.filter(status=sale_status)

        payment_status = request.query_params.get("payment_status")
        if payment_status:
            qs = qs.filter(payment_status=payment_status)

        data = [
            {
                "id": s.pk,
                "type": s.type,
                "status": s.status,
                "total": s.total,
                "amount_paid": s.amount_paid,
                "remaining": s.remaining,
                "payment_status": s.payment_status,
                "agent_name": s.agent.user.get_full_name() if s.agent else None,
                "delivery_address": s.delivery_address,
                "created_at": s.created_at,
                "delivered_at": s.delivered_at,
            }
            for s in qs
        ]
        return Response(data)


# ---------------------------------------------------------------------------
# GET /clients/map  — GeoJSON des clients géolocalisés
# ---------------------------------------------------------------------------
class ClientMapView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "clients.map"

    @extend_schema(
        responses={"200": {"type": "object"}},
        summary="Carte des clients (GeoJSON)",
        description="Retourne un FeatureCollection GeoJSON de tous les clients ayant des coordonnées.",
        parameters=[
            OpenApiParameter(
                "establishment_type", str,
                description="Filtrer par type (bar, restaurant, cafeteria, boutique, autre)",
            ),
            OpenApiParameter("agent_id", int, description="Filtrer par agent (clients de ses livraisons)"),
        ],
    )
    def get(self, request):
        from sales.models import Sale

        qs = Client.objects.select_related("user").exclude(
            latitude__isnull=True
        ).exclude(longitude__isnull=True)

        establishment_type = request.query_params.get("establishment_type")
        if establishment_type:
            qs = qs.filter(establishment_type=establishment_type)

        agent_id = request.query_params.get("agent_id")
        if agent_id:
            client_ids = Sale.objects.filter(
                agent_id=agent_id
            ).values_list("client_id", flat=True).distinct()
            qs = qs.filter(pk__in=client_ids)

        features = [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(c.longitude), float(c.latitude)],
                },
                "properties": {
                    "id": c.pk,
                    "business_name": c.business_name,
                    "manager_name": c.manager_name,
                    "establishment_type": c.establishment_type,
                    "address": c.address,
                    "email": c.user.email,
                    "phone": c.user.phone,
                },
            }
            for c in qs
        ]

        return Response({"type": "FeatureCollection", "features": features})


# ---------------------------------------------------------------------------
# GET  /clients/{id}/delivery-points
# POST /clients/{id}/delivery-points
# ---------------------------------------------------------------------------
class DeliveryPointListCreateView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "delivery_points.manage"

    @extend_schema(
        responses=DeliveryPointSerializer(many=True),
        summary="Lister les points de livraison d'un client",
        description="Client : les siens uniquement. Admin et gestionnaire : tous.",
    )
    def get(self, request, pk):
        client = _get_client(pk)
        if not client:
            return Response({"detail": "Client introuvable."}, status=status.HTTP_404_NOT_FOUND)

        if request.user.role.code == "client" and client.user_id != request.user.pk:
            return Response({"detail": "Permission refusée."}, status=status.HTTP_403_FORBIDDEN)

        qs = DeliveryPoint.objects.filter(client=client).order_by("-is_default", "label")
        return Response(DeliveryPointSerializer(qs, many=True).data)

    @extend_schema(
        request=DeliveryPointCreateSerializer,
        responses={201: DeliveryPointSerializer},
        summary="Ajouter un point de livraison",
        description=(
            "Crée un point de livraison pour le client. "
            "Si `is_default=true`, les autres points du même client sont désactivés comme défaut."
        ),
    )
    def post(self, request, pk):
        client = _get_client(pk)
        if not client:
            return Response({"detail": "Client introuvable."}, status=status.HTTP_404_NOT_FOUND)

        # Un client peut ajouter ses propres points ; admin/gestionnaire peuvent en ajouter pour n'importe quel client
        if request.user.role.code == "client" and client.user_id != request.user.pk:
            return Response({"detail": "Permission refusée."}, status=status.HTTP_403_FORBIDDEN)

        serializer = DeliveryPointCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Si ce point est défini comme défaut, retirer l'ancien défaut
        if serializer.validated_data.get("is_default"):
            DeliveryPoint.objects.filter(client=client, is_default=True).update(is_default=False)

        point = serializer.save(client=client)
        return Response(DeliveryPointSerializer(point).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# PATCH  /delivery-points/{id}
# DELETE /delivery-points/{id}
# ---------------------------------------------------------------------------
class DeliveryPointDetailView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "delivery_points.manage"

    def _get_point(self, pk):
        try:
            return DeliveryPoint.objects.select_related("client__user").get(pk=pk)
        except DeliveryPoint.DoesNotExist:
            return None

    def _check_ownership(self, request, point):
        """Retourne True si le client connecté est bien le propriétaire du point."""
        if request.user.role.code == "client":
            return point.client.user_id == request.user.pk
        return True

    @extend_schema(
        request=DeliveryPointUpdateSerializer,
        responses=DeliveryPointSerializer,
        summary="Modifier un point de livraison",
    )
    def patch(self, request, pk):
        point = self._get_point(pk)
        if not point:
            return Response({"detail": "Point de livraison introuvable."}, status=status.HTTP_404_NOT_FOUND)

        if not self._check_ownership(request, point):
            return Response({"detail": "Permission refusée."}, status=status.HTTP_403_FORBIDDEN)

        serializer = DeliveryPointUpdateSerializer(point, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        # Si on active ce point comme défaut, retirer l'ancien
        if serializer.validated_data.get("is_default"):
            DeliveryPoint.objects.filter(
                client=point.client, is_default=True
            ).exclude(pk=point.pk).update(is_default=False)

        serializer.save()
        point.refresh_from_db()
        return Response(DeliveryPointSerializer(point).data)

    @extend_schema(
        responses={204: None},
        summary="Supprimer un point de livraison",
        description="Interdit si ce point est référencé par une vente.",
    )
    def delete(self, request, pk):
        point = self._get_point(pk)
        if not point:
            return Response({"detail": "Point de livraison introuvable."}, status=status.HTTP_404_NOT_FOUND)

        if not self._check_ownership(request, point):
            return Response({"detail": "Permission refusée."}, status=status.HTTP_403_FORBIDDEN)

        # Refuser la suppression si le point est lié à une vente
        from sales.models import Sale
        if Sale.objects.filter(delivery_point=point).exists():
            return Response(
                {"detail": "Ce point de livraison est lié à une vente et ne peut pas être supprimé."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        point.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
