from rest_framework.permissions import BasePermission
from bookshelf.models import BookStatus


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



class IsFileAuthor(BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.user.is_superuser or request.user == obj.book.user
    

class IsBookCreator(BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.user.is_superuser or request.user == obj.user

  
class PublicOrPrivate(BasePermission):
    def has_object_permission(self, request, view, obj):
        if obj.status == BookStatus.PUBLIC:
            return True
        elif obj.status == BookStatus.PRIVATE:
            return request.user == obj.user