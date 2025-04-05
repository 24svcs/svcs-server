from rest_framework.throttling import UserRateThrottle, AnonRateThrottle

class BurstRateThrottle(UserRateThrottle):
    """
    Throttle for short burst of requests - protects against rapid-fire API calls
    Limits authenticated users to 60 requests per minute
    """
    scope = 'burst'
    rate = '60/min'

class SustainedRateThrottle(UserRateThrottle):
    """
    Throttle for sustained activity - protects against constant high-volume requests
    Limits authenticated users to 1000 requests per day
    """
    scope = 'sustained'
    rate = '1000/day'

class AnonymousRateThrottle(AnonRateThrottle):
    """
    Throttle for unauthenticated requests
    Limits anonymous users to 20 requests per hour
    """
    rate = '20/hour' 