from django.utils import timezone
import pytz
from datetime import datetime

def convert_datetime_to_timezone(dt, target_timezone=None):
    """
    Convert a datetime object to the target timezone
    
    Args:
        dt: A datetime object or ISO 8601 string
        target_timezone: A pytz timezone object or string (defaults to UTC)
    
    Returns:
        A timezone-aware datetime object in the target timezone
    """
    if target_timezone is None:
        target_timezone = pytz.UTC
    elif isinstance(target_timezone, str):
        target_timezone = pytz.timezone(target_timezone)
    
    # Handle string input
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
    
    # Make sure the datetime is timezone-aware
    if dt.tzinfo is None:
        dt = timezone.make_aware(dt, pytz.UTC)
    
    # Convert to target timezone
    return dt.astimezone(target_timezone) 