from rest_framework import permissions
from organization.models import Member

class OrganizationPermission(permissions.BasePermission):
    """
    Custom permission class for organization-related operations with optimized queries.
    """
    
    def __init__(self, required_permission=None):
        self.required_permission = required_permission
        # Cache for permission checks to avoid repeated queries
        self._member_cache = {}
        self._permission_cache = {}
        
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return request.user.is_authenticated
        return request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
            
        user = request.user
        
        # Get the organization from the object
        if hasattr(obj, 'organization'):
            organization = obj.organization
        else:
            organization = obj
            
        # Staff with appropriate permissions can do anything
        if user.is_staff and user.has_perm(f'{organization._meta.app_label}.change_{organization._meta.model_name}'):
            return True
        
        # Use cache key based on user and organization
        cache_key = f"{user.id}_{organization.id}"
        
        # Check if we've already queried this user's membership for this organization
        if cache_key in self._member_cache:
            member = self._member_cache[cache_key]
        else:
            # Query the member directly with all permissions in a single query
            try:
                member = Member.objects.select_related(
                    'organization', 'user'
                ).prefetch_related(
                    'permissions'
                ).get(
                    user=user,
                    organization=organization
                )
                # Cache the result
                self._member_cache[cache_key] = member
                
                # Pre-cache all permissions for this member
                permission_names = set(perm.name for perm in member.permissions.all())
                self._permission_cache[cache_key] = permission_names
                
            except Member.DoesNotExist:
                # No membership found
                return False
        
        # Owners can do anything
        if member.is_owner:
            return True
            
        # Admins must be active
        if member.is_admin and member.status == Member.ACTIVE:
            return True
            
        # If no specific permission is required, deny access to regular members
        if not self.required_permission:
            return False
            
        # Check if user has the required permission
        if member.status != Member.ACTIVE:
            return False
            
        # Use cached permissions instead of making a new query
        if cache_key in self._permission_cache:
            return self.required_permission in self._permission_cache[cache_key]
        
        # Fallback to database query if cache is not available
        return member.permissions.filter(name=self.required_permission).exists()