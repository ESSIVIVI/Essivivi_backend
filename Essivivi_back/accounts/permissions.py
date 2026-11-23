from rest_framework.permissions import BasePermission


class HasPermission(BasePermission):
    """Autorise l'accès si le rôle de l'utilisateur a le switch `view.required_permission`.

    Usage :
        class StockView(APIView):
            permission_classes = [HasPermission]
            required_permission = "stock.view"

    La portée (« siennes », « affectées »…) se règle ensuite dans get_queryset().
    """

    def has_permission(self, request, view):
        code = getattr(view, "required_permission", None)
        user = request.user
        return bool(code and user and user.is_authenticated and user.has_permission(code))
