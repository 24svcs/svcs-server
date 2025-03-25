import jwt
import requests
from django.core.cache import cache
from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from .models import User
import time
from django.db import transaction
import logging

CLERK_JWKS_TTL = 3600 

logger = logging.getLogger(__name__)

class ClerkAuthentication(BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return None

        token = auth_header.split(" ")[1]

        try:
            # Get token header to find the 'kid'
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get("kid")
            if not kid:
                raise AuthenticationFailed("Missing 'kid' in token header")

            # Try fetching JWKS from cache
            jwks = cache.get(settings.CLERK_JWKS_CACHE_KEY)
            if not jwks:
                # Fetch JWKS from Clerk
                retry_count = 0
                max_retries = 3
                while retry_count < max_retries:
                    try:
                        response = requests.get(settings.CLERK_JWKS_URL, timeout=5)
                        response.raise_for_status()
                        break
                    except requests.RequestException:
                        retry_count += 1
                        if retry_count == max_retries:
                            raise
                        time.sleep(0.5)  # Short delay before retry
                jwks = response.json()
                cache.set(settings.CLERK_JWKS_CACHE_KEY, jwks, CLERK_JWKS_TTL)  # Cache it

            # Validate JWKS response
            if "keys" not in jwks:
                raise AuthenticationFailed("Invalid JWKS format")

            # Find the matching key
            public_key = None
            for key in jwks["keys"]:
                if key.get("kid") == kid:
                    public_key = jwt.PyJWK(key).key
                    break
            
            if not public_key:
                raise AuthenticationFailed("No matching key found in JWKS")

            # Decode and verify token
            decoded_token = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                issuer=settings.CLERK_ISSUER,
                audience=settings.CLERK_AUDIENCE,
                options={"verify_signature": True},
                leeway=30  # 30 seconds leeway for clock skew
            )

            # Extract user details
            user_id = decoded_token.get("sub")  
            email = decoded_token.get("email")
            username = decoded_token.get("username") or email 
            first_name = decoded_token.get("first_name", "")
            last_name = decoded_token.get("last_name", "")
            image_url = decoded_token.get("image_url", "")

            if not user_id or not email:
                raise AuthenticationFailed("Invalid token: Missing Key Informations")

            # Create or update the user
            with transaction.atomic():
                user, _ = User.objects.get_or_create(
                   id=user_id,
                    defaults={"email": email, "first_name": first_name, "last_name": last_name, 'username':username, 'image_url':image_url},
                )

            return user, None

        except jwt.ExpiredSignatureError:
            logger.warning(f"Token expired for request to {request.path}")
            raise AuthenticationFailed("Token expired")
        except jwt.InvalidTokenError:
            raise AuthenticationFailed("Invalid token")
        except requests.RequestException:
            raise AuthenticationFailed("Unable to fetch JWKS")
        except ValueError as e:
            raise AuthenticationFailed(f"Invalid JWK format ({str(e)})")