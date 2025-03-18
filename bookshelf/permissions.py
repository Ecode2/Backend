from rest_framework.permissions import BasePermission

class IsFileAuthor(BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.user.is_superuser or request.user == obj.book.user
    

class IsBookCreator(BasePermission):
    def has_object_permission(self, request, view, obj):

        if request.method in ("PATCH", "PUT", "DELETE"):
            return request.user.is_superuser or obj.user == request.user
        
        return True


class PublicOrPrivate(BasePermission):
    def has_object_permission(self, request, view, obj):

        if obj.status == "public":
            return True
        
        return obj.user == request.user