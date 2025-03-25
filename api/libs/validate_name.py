from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from organization.models import Organization
import re

def validate_organization_name(value, instance=None):
    """
    Validates a organization name against various criteria:
    - Uniqueness (no duplicate organization names)
    - Character set validation (allows letters, numbers, and appropriate punctuation)
    - Length requirements (6-50 characters)
    - Formatting rules (no excessive whitespace, no leading/trailing punctuation)
    - Business suffix validation (requires meaningful content before suffixes)
    - Prevention of generic-only names
    
    Args:
        value: The company name to validate
        instance: Optional. When updating an existing company, this parameter
                 should be the company instance being updated to exclude it
                 from the uniqueness check.
    
    Returns:
        The validated company name.
    
    Raises:
        ValidationError: If the company name fails any validation checks.
    """
    value = value.strip()
    
    # Check for existing company with same name
    query = Organization.objects.filter(name__iexact=value)
    if instance:
        query = query.exclude(id=instance.id)
    if query.exists():
        raise serializers.ValidationError(_('A company with this name already exists.'))
    
    # Basic character validation - expanded to include more valid punctuation and international characters
    if not re.match(r'^[a-zA-Z0-9\s\.\&\-\',\(\)@_+]+$', value):
        raise serializers.ValidationError(_('Name can only contain letters, numbers, spaces, and basic punctuation (., &, -, \', (, ), @, _, +).'))
    
    # Ensure name contains at least one letter
    if not re.search(r'[a-zA-Z]', value):
        raise serializers.ValidationError(_('Name must contain at least one alphabetic character.'))
    
    # Length validation
    if len(value) < 6:
        raise serializers.ValidationError(_('Name must be at least 6 characters long.'))
    if len(value) > 50:
        raise serializers.ValidationError(_('Name cannot exceed 50 characters.'))
    
    # Check for excessive whitespace
    if re.search(r'\s{2,}', value):
        raise serializers.ValidationError(_('Name cannot contain consecutive spaces.'))
    
    # Check for consecutive punctuation
    if re.search(r'[\.\&\-\'\,\(\)]{2,}', value):
        raise serializers.ValidationError(_('Name cannot contain consecutive or non-standard punctuation characters.'))
    
    # Check for leading/trailing punctuation
    if re.match(r'^[\.\&\-\'\,\(\)]', value) or re.search(r'[\.\&\-\'\,\(\)]$', value):
        raise serializers.ValidationError(_('Name cannot start or end with punctuation.'))
    
    # Check for common business terms at the end
    common_suffixes = [
        'llc', 'inc', 'ltd', 'corporation', 'corp', 'company', 'co', 'sa', 'gmbh', 'ag', 'plc', 'llp', 'sarl'
    ]
    name_lower = value.lower()
    for suffix in common_suffixes:
        if name_lower.endswith(suffix) and (len(name_lower) == len(suffix) or name_lower[-len(suffix)-1] in [' ', '.', ',']):
            # Validate that there's substantial content before the suffix
            prefix = name_lower[:-len(suffix)].strip(' .,')
            if len(prefix) < 3:
                raise serializers.ValidationError(_('Company name needs more content before the business suffix.'))
    
    # Prevent names that are just generic terms
    generic_terms = ['company', 'business', 'enterprise', 'organization', 'corporation', 'consultancy', 'services']
    if name_lower.strip() in generic_terms:
        raise serializers.ValidationError(_('Company name cannot be a generic term.'))
    
    return value
