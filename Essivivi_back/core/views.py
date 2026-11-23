from django.db import connection
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@extend_schema(responses={200: OpenApiTypes.OBJECT}, auth=[])
@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    """Vérifie que l'API et la base de données répondent."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return Response({"status": "ok"})
