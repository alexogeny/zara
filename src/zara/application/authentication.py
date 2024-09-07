import asyncio
import base64
import hashlib
import hmac
import json
import ssl
import urllib.request
from functools import wraps
from typing import Callable, Dict, List

SECRET_KEY = "your_application_secret"
ALGORITHM = "HS256"
KEYCLOAK_URL = "http://localhost:8080/realms/master/protocol/openid-connect/token"
CLIENT_ID = "local"
CLIENT_SECRET = "U5JroKat0RTxakkITDPvbva0REoHVuOe"  # If necessary
REDIRECT_URI = "http://localhost:8000/callback"


# Helper function to create JWT
def create_jwt(payload: Dict, secret: str, algorithm: str = "HS256") -> str:
    header = {"alg": algorithm, "typ": "JWT"}

    # Encode header and payload as base64url
    header_b64 = (
        base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    )
    payload_b64 = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )

    # Create the signature
    signature = hmac.new(
        secret.encode(), f"{header_b64}.{payload_b64}".encode(), hashlib.sha256
    ).digest()
    signature_b64 = base64.urlsafe_b64encode(signature).decode().rstrip("=")

    # Return the full JWT
    return f"{header_b64}.{payload_b64}.{signature_b64}"


# Dummy function to verify username and password
def verify_credentials(username: str, password: str) -> Dict:
    # Replace this with a real user lookup in your database
    if username == "testuser" and password == "password123":
        return {"username": username, "roles": ["user"], "permissions": ["read"]}
    return None


async def get_keycloak_token(username: str, password: str) -> dict:
    data = {
        "client_id": CLIENT_ID,
        "username": username,
        "password": password,
        "grant_type": "password",
        "client_secret": CLIENT_SECRET,  # Only if necessary
        "redirect_uri": REDIRECT_URI,  # If necessary
    }

    # Encode the data for the POST request
    encoded_data = urllib.parse.urlencode(data).encode()

    # Make the request to Keycloak's token endpoint
    async def fetch_token():
        req = urllib.request.Request(KEYCLOAK_URL, data=encoded_data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        context = (
            ssl._create_unverified_context()
        )  # To avoid SSL verification for local testing

        with urllib.request.urlopen(req, context=context) as response:
            return json.loads(response.read().decode())

    # Run in a thread to avoid blocking
    return await fetch_token()


# Helper function to decode base64url safely
def base64url_decode(input):
    rem = len(input) % 4
    if rem > 0:
        input += "=" * (4 - rem)
    return base64.urlsafe_b64decode(input)


# Helper function to fetch OpenID Connect configuration (asynchronous)
async def fetch_openid_configuration(issuer_url: str):
    openid_config_url = f"{issuer_url}/.well-known/openid-configuration"
    return await asyncio.to_thread(_sync_fetch_openid_config, openid_config_url)


# Synchronous helper to fetch openid configuration
def _sync_fetch_openid_config(openid_config_url):
    with urllib.request.urlopen(
        openid_config_url, context=ssl._create_unverified_context()
    ) as response:
        return json.loads(response.read().decode())


# Helper function to fetch public key from the JWKS endpoint (asynchronous)
async def fetch_public_key(jwks_uri: str, kid: str):
    return await asyncio.to_thread(_sync_fetch_public_key, jwks_uri, kid)


# Synchronous helper to fetch public key
def _sync_fetch_public_key(jwks_uri, kid):
    with urllib.request.urlopen(
        jwks_uri, context=ssl._create_unverified_context()
    ) as response:
        jwks = json.loads(response.read().decode())

    # Find the key by kid
    for key in jwks["keys"]:
        if key["kid"] == kid:
            return key

    raise ValueError("No matching key found")


# Verify the JWT signature (simplified, using HMAC for local testing)
def verify_signature(header, payload, signature, secret):
    signing_input = f"{header}.{payload}".encode("utf-8")
    calculated_signature = base64url_decode(
        hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    )
    return hmac.compare_digest(calculated_signature, base64url_decode(signature))


# The decorator to use for ASGI endpoints
def auth_required(roles: List[str] = None, permissions: List[str] = None):
    roles = roles or []
    permissions = permissions or []

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(request):
            request.logger.warning(request.headers)
            authorization = request.headers.get(b"Authorization", "")
            if not authorization.startswith(b"Bearer "):
                raise ValueError("Authorization header missing or malformed")

            request.logger.warning(authorization)
            token = authorization.decode("utf-8").split(" ")[1]
            try:
                # Split the JWT token into parts
                header_b64, payload_b64, signature_b64 = token.split(".")

                # Decode header and payload
                header = json.loads(base64url_decode(header_b64).decode("utf-8"))
                payload = json.loads(base64url_decode(payload_b64).decode("utf-8"))

                if payload is None:
                    raise ValueError("JWT payload is empty")

                request.logger.warning(payload)

                # Fetch OpenID Configuration from Keycloak asynchronously
                issuer_url = "http://localhost:8080/realms/master"
                openid_config = await fetch_openid_configuration(issuer_url)
                jwks_uri = openid_config["jwks_uri"]

                # Fetch the public key asynchronously
                kid = header["kid"]
                public_key = await fetch_public_key(jwks_uri, kid)

                # Verify the signature (simplified for local testing)
                if not verify_signature(
                    header_b64, payload_b64, signature_b64, "your_application_secret"
                ):
                    raise ValueError("Invalid JWT signature")

                # Check roles
                user_roles = payload.get("roles", [])
                if not any(role in user_roles for role in roles):
                    raise ValueError("User does not have required roles")

                # Check permissions
                user_permissions = payload.get("permissions", [])
                if not any(perm in user_permissions for perm in permissions):
                    raise ValueError("User does not have required permissions")

                # Attach the user info to the request
                request.user = payload

                return await func(request)

            except (ValueError, KeyError) as e:
                raise ValueError(f"Authorization failed: {str(e)}")

        return wrapper

    return decorator
