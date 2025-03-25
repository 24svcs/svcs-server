from organization.models import Organization
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
import re

def validate_organization_namespace(value, instance=None):
    """
    Validates a organization name space that will be used in URLs (e.g., domain.com/organization-name-space).
    
    Ensures the name space:
    - Is unique across all organizations
    - Contains only URL-safe characters (letters, numbers, hyphens, underscores, and periods)
    - Has appropriate length (6-30 characters)
    - Is not a reserved word that could conflict with system routes
    - Contains at least one letter
    
    Args:
        value: The organization name space to validate
        instance: Optional. When updating an existing organization, this parameter
                 should be the organization instance being updated to exclude it
                 from the uniqueness check.
    
    Returns:
        The validated, lowercase organization name space.
    
    Raises:
        ValidationError: If the organization name space fails any validation checks.
    """
    # Normalize to lowercase for URL consistency
    value = value.lower().strip()
    
    # Check for existing organization with same name space
    query = Organization.objects.filter(name_space__iexact=value)
    if instance:
        query = query.exclude(id=instance.id)
    if query.exists():
        raise serializers.ValidationError(_('A organization with this name space already exists.'))
    
    # Character validation for URL safety - now including hyphens, underscores, and periods
    if not re.match(r'^[a-z0-9\-._]+$', value):
        raise serializers.ValidationError(_('Name space can only contain lowercase letters, numbers, hyphens, periods, and underscores.'))
    
    # Check to prevent name space consisting only of hyphens
    if value == '-' * len(value):
        raise serializers.ValidationError(_('Name space cannot consist only of hyphens.'))
    
    # Ensure name space contains at least one letter
    if not re.search(r'[a-z]', value):
        raise serializers.ValidationError(_('Name space must contain at least one letter.'))
    
    # Length validation
    if len(value) < 6:
        raise serializers.ValidationError(_('Name space must be at least 6 characters long.'))
    if len(value) > 64:
        raise serializers.ValidationError(_('Name space cannot exceed 64 characters.'))
    
    # Check for reserved words that shouldn't be used in URLs
    reserved_words = [
        'admin', 'api', 'auth', 'login', 'logout', 'register', 
        'dashboard', 'settings', 'profile', 'account', 'billing',
        'help', 'support', 'about', 'terms', 'privacy', 'home',
        'index', 'search', 'static', 'media', 'public', 'private',
        'internal', 'external', 'system', 'default', 'test', 'demo'
    ]
    
    if value in reserved_words:
        raise serializers.ValidationError(_('This name space is reserved and cannot be used. Please choose another one.'))
    
    # Check that it doesn't start with a number (good practice for identifiers)
    if re.match(r'^[0-9]', value):
        raise serializers.ValidationError(_('Name space should not start with a number.'))
    
    # Check for consecutive hyphens
    if '--' in value:
        raise serializers.ValidationError(_('Name space cannot contain consecutive hyphens.'))
    
    # Check for leading/trailing hyphens
    if value.startswith('-') or value.endswith('-'):
        raise serializers.ValidationError(_('Name space cannot start or end with a hyphen.'))
    
    return value
