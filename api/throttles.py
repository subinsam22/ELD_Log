# throttles.py
from rest_framework.throttling import SimpleRateThrottle

class PlanTripRateThrottle(SimpleRateThrottle):
    
    scope = 'plan-trip'
    
    def get_cache_key(self, request, view):
        # Use IP address as the throttle key
        if request.user and request.user.is_authenticated:
            # If user is authenticated, use user ID
            return self.cache_format % {
                'scope': self.scope,
                'ident': request.user.pk
            }
        # For anonymous users, use IP address
        return self.cache_format % {
            'scope': self.scope,
            'ident': self.get_ident(request)
        }