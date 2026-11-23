from django.contrib import admin

from .models import Client, DeliveryPoint

admin.site.register([Client, DeliveryPoint])
