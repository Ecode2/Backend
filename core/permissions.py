from rest_framework.permissions import BasePermission


class IsAdminUser(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "admin"


class IsStaffUser(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "staff"


class IsAdminOrStaff(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == "staff"
            or request.user.is_authenticated
            and request.user.role == "admin"
        )


class IsCustomerUser(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "customer"


class IsAuthor(BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.user == obj.user

class IsFileAuthor(BasePermission):
    def has_object_permission(self, request, view, obj):
        user = obj.book
        return request.user == obj.book.user
