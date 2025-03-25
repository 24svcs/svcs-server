
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
import re
from organization.models import Organization

def validate_tax_id(value, instance=None):
    """
    Validates a company tax ID against various criteria:
    - Format validation (based on common tax ID formats)
    - Uniqueness (no duplicate tax IDs across companies)
    - Character validation (ensures only valid characters are used)
    
    Args:
        value: The company tax ID to validate
        instance: Optional. When updating an existing company, this parameter
                 should be the company instance being updated to exclude it
                 from the uniqueness check.
    
    Returns:
        The validated tax ID.
    
    Raises:
        ValidationError: If the tax ID fails any validation checks.
    """
    if not value:
        return value
        
    # Normalize tax ID by removing common formatting characters and converting to uppercase
    normalized_value = re.sub(r'[\s\-\.]+', '', value).upper()
    
    # Check if the tax ID is empty after normalization
    if not normalized_value:
        raise serializers.ValidationError(_('Tax ID cannot be empty.'))
    
    # Check for uniqueness if tax ID is being validated
    if normalized_value:
        query = Organization.objects.filter(tax_id__iexact=normalized_value)
        if instance:
            query = query.exclude(id=instance.id)
        if query.exists():
            raise serializers.ValidationError(_('A organization with this tax ID already exists.'))
    
    # Basic character validation - should only contain alphanumeric characters
    if not re.match(r'^[A-Z0-9]+$', normalized_value):
        raise serializers.ValidationError(_('Tax ID can only contain letters and numbers.'))
    
    # Length validation - most tax IDs are between 8-20 characters
    if not (8 <= len(normalized_value) <= 20):
        raise serializers.ValidationError(_('Tax ID must be between 8 and 20 characters after normalization.'))
    
    # Check for invalid patterns (all same digits, sequential digits)
    if re.match(r'^(.)\1+$', normalized_value):
        raise serializers.ValidationError(_('Tax ID cannot consist of all the same character.'))
    
    # Check for common fake patterns
    obvious_fakes = ['12345678', '87654321', 'TAXNUMBER', 'ABCDEFGH']
    if normalized_value in obvious_fakes:
        raise serializers.ValidationError(_('Please enter a valid tax ID.'))
    
    # Additional format checks could be added here for specific country tax ID formats
    # For example, for US EIN: XX-XXXXXXX
    # For UK VAT: GB XXX XXXX XX or GBXX XXXX XX
    
    return normalized_value


