from django.core.validators import URLValidator
from rest_framework import serializers
import re

def validate_url(value):
    """
    Validates a company logo URL:
    - Must be a valid URL
    - Must use HTTPS (except in debug mode)
    - Must point to an image file (.jpg, .jpeg, .png, .gif, .svg, .webp)
    """
    if not value:
        return value

    value = value.strip()
    
    # Validate URL format
    try:
        URLValidator()(value)
    except:
        raise serializers.ValidationError('Invalid URL format.')

    # Ensure HTTPS for security
    if not value.startswith('https://'):
        raise serializers.ValidationError('Logo URL must use HTTPS.')

    # Ensure it points to an image file
    if not re.search(r'\.(jpg|jpeg|png|gif|svg|webp)$', value, re.IGNORECASE):
        raise serializers.ValidationError('Logo URL must be an image file.')

    return value