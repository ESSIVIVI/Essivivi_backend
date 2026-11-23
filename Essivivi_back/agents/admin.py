from django.contrib import admin

from .models import Agent, AgentLocation, AgentPayHistory, AgentPayout

admin.site.register([Agent, AgentLocation, AgentPayout, AgentPayHistory])
