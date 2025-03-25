import pytz
from rest_framework.exceptions import ValidationError

class TimezoneMixin:
    """
    Mixin to handle timezone parameters in API requests
    """
    def get_timezone_from_request(self):
        """
        Get timezone from request query parameters or use authenticated user's timezone
        """
        # First check if timezone is specified in query parameters
        tz_param = self.request.query_params.get('timezone')
        if tz_param:
            try:
                return pytz.timezone(tz_param)
            except pytz.exceptions.UnknownTimeZoneError:
                raise ValidationError(f"Invalid timezone: {tz_param}")
        
        # Otherwise use authenticated user's timezone
        if self.request.user.is_authenticated:
            return self.request.user.timezone
        
        # Default to UTC - use pytz.UTC, not timezone.utc
        return pytz.UTC
    
    def get_serializer_context(self):
        """
        Add timezone to serializer context
        """
        context = super().get_serializer_context()
        context['timezone'] = self.get_timezone_from_request()
        return context 