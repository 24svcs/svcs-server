from django.core.validators import URLValidator
from rest_framework import serializers
import re

def validate_url(value):
    """
    Validates a company logo URL or uploaded file:
    - For URLs: Must be a valid URL, use HTTPS, and point to an image file
    - For uploads: Must be an image file
    """
    if not value:
        return value

    # Handle file uploads
    if hasattr(value, 'name'):
        # It's a file upload
        if not value.name.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp')):
            raise serializers.ValidationError('File must be an image (.jpg, .jpeg, .png, .gif, .svg, .webp)')
        return value

    # Handle URL strings
    if isinstance(value, str):
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