from django.urls import path

from .views import (
    DrinkDeactivateView,
    DrinkDetailView,
    DrinkListCreateView,
    StockAdjustView,
    StockListView,
    StockMovementListView,
    StockRestockView,
)

urlpatterns = [
    # Boissons
    path("drinks", DrinkListCreateView.as_view(), name="drink-list-create"),
    path("drinks/<int:pk>", DrinkDetailView.as_view(), name="drink-detail"),
    path("drinks/<int:pk>/deactivate", DrinkDeactivateView.as_view(), name="drink-deactivate"),

    # Stock
    path("stock", StockListView.as_view(), name="stock-list"),
    path("stock/restock", StockRestockView.as_view(), name="stock-restock"),
    path("stock/adjust", StockAdjustView.as_view(), name="stock-adjust"),
    path("stock/movements", StockMovementListView.as_view(), name="stock-movements"),
]
