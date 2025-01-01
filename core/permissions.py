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



class IsFileAuthor(BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.user.is_superuser or request.user == obj.book.user
    

class IsBookCreator(BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.user.is_superuser or request.user == obj.user

  
class PublicOrPrivate(BasePermission):
    def has_object_permission(self, request, view, obj):
        if obj.status == "public":
            return True
        elif obj.status == "private":
            return request.user == obj.user
        
    def has_permission(self, request, view):
        return True