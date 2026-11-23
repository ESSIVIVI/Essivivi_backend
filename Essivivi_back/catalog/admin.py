from django.contrib import admin

from .models import Drink, Stock, StockMovement

admin.site.register([Drink, Stock, StockMovement])
