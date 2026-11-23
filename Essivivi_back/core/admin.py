from django.contrib import admin

from .models import ActivityLog, Notification, PlatformSetting

admin.site.register([Notification, ActivityLog, PlatformSetting])
