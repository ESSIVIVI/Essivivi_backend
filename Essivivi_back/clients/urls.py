from django.urls import path

from .views import (
    ClientDetailView,
    ClientListView,
    ClientMapView,
    ClientSalesView,
    DeliveryPointDetailView,
    DeliveryPointListCreateView,
)

urlpatterns = [
    path("clients", ClientListView.as_view(), name="client-list"),
    path("clients/map", ClientMapView.as_view(), name="client-map"),
    path("clients/<int:pk>", ClientDetailView.as_view(), name="client-detail"),
    path("clients/<int:pk>/sales", ClientSalesView.as_view(), name="client-sales"),
    path("clients/<int:pk>/delivery-points", DeliveryPointListCreateView.as_view(), name="delivery-point-list-create"),
    path("delivery-points/<int:pk>", DeliveryPointDetailView.as_view(), name="delivery-point-detail"),
]
