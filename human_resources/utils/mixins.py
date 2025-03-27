import pytz
from organization.models import Preference
from django.core.cache import cache


class OrganizationTimezoneMixin:
    def _get_organization_timezone(self, organization_id):
        """
        Helper method to get the organization's timezone.
        Uses caching to reduce database queries.
        """
        cache_key = f"org_timezone_{organization_id}"
        cached_timezone = cache.get(cache_key)
        
        if cached_timezone:
            return pytz.timezone(str(cached_timezone))  # Convert to string first
        
        try:
            org_preferences = Preference.objects.select_related('organization').get(
                organization_id=organization_id
            )
            # Convert timezone to string first
            timezone_str = str(org_preferences.timezone)
            organization_timezone = pytz.timezone(timezone_str)
            
            # Cache the timezone string
            cache.set(cache_key, timezone_str, 3600)
            
            return organization_timezone
        except Preference.DoesNotExist:
            # Default to UTC if preferences not found
            return pytz.UTC

    def _make_aware(self, naive_datetime, timezone):
        """Helper method to make a naive datetime timezone-aware"""
        if isinstance(timezone, str):
            timezone = pytz.timezone(timezone)
        return timezone.localize(naive_datetime) if hasattr(timezone, 'localize') else pytz.UTC.localize(naive_datetime)