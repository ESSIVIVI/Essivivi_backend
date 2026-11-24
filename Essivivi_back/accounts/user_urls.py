from django.urls import path

from .user_views import (
    RolePermissionSwitchView,
    RolesMatrixView,
    UserActivateView,
    UserDeactivateView,
    UserDeleteView,
    UserDetailView,
    UserListView,
    UserReset2FAView,
    UserResetPasswordView,
    UserRoleView,
)

urlpatterns = [
    # Utilisateurs
    path("users", UserListView.as_view(), name="user-list"),
    path("users/<int:pk>", UserDetailView.as_view(), name="user-detail"),
    path("users/<int:pk>/deactivate", UserDeactivateView.as_view(), name="user-deactivate"),
    path("users/<int:pk>/activate", UserActivateView.as_view(), name="user-activate"),
    path("users/<int:pk>/delete", UserDeleteView.as_view(), name="user-delete"),
    path("users/<int:pk>/role", UserRoleView.as_view(), name="user-role"),
    path("users/<int:pk>/reset-password", UserResetPasswordView.as_view(), name="user-reset-password"),
    path("users/<int:pk>/reset-2fa", UserReset2FAView.as_view(), name="user-reset-2fa"),

    # Matrice rôles / permissions
    path("roles/matrix", RolesMatrixView.as_view(), name="roles-matrix"),
    path("roles/<int:role_id>/permissions/<int:perm_id>", RolePermissionSwitchView.as_view(), name="role-permission-switch"),
]
