import re
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from phonenumbers import parse, is_valid_number, NumberParseException, format_number, PhoneNumberFormat, region_code_for_number

def validate_phone(value, default_region='IN'):
    if default_region not in region_code_for_number:
        raise serializers.ValidationError(_('Invalid region code.'))
        
    try:
        # Normalize phone number by removing common formatting characters
        normalized_value = re.sub(r'[\s\-\(\)\.]+', '', value)
        
        # Parse number with a default region if no country code provided
        phone_number = parse(normalized_value, default_region)
        
        if not is_valid_number(phone_number):
            raise serializers.ValidationError(_('Please enter a valid phone number.'))
        
        # if len(str(phone_number.national_number)) != 10:
        #     raise serializers.ValidationError(_('Phone number must be 10 digits long for this region.'))
            

        return format_number(phone_number, PhoneNumberFormat.E164)
        
    except NumberParseException:
        raise serializers.ValidationError(_('Please enter a valid phone number format.'))
