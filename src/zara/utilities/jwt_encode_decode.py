import asyncio
import base64
import hashlib
import hmac
import json
import os
import secrets
import ssl
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Dict

import argon2
import orjson
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from zara.utilities.context import Context


def load_rsa_public_key(jwk: dict):
    """
    Converts a JWKS (JSON Web Key Set) public key into an RSA key.
    Assumes the key is in the JWKS format.
    """
    n = base64.urlsafe_b64decode(jwk["n"] + "==")  # 'n' is the modulus
    e = base64.urlsafe_b64decode(jwk["e"] + "==")  # 'e' is the public exponent

    # Convert 'n' and 'e' into an RSA public key object
    public_numbers = rsa.RSAPublicNumbers(
        int.from_bytes(e, "big"), int.from_bytes(n, "big")
    )
    public_key = public_numbers.public_key(backend=default_backend())

    return public_key


def verify_rs256_signature(
    header_b64: str, payload_b64: str, signature_b64: str, public_key
) -> bool:
    """
    Verifies an RS256 JWT signature using the provided RSA public key.
    """
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    signature = base64.urlsafe_b64decode(signature_b64 + "==")  # Add padding if missing

    try:
        # Verify the signature using RSA public key
        public_key.verify(signature, signing_input, padding.PKCS1v15(), hashes.SHA256())
        return True  # Signature is valid
    except Exception:
        return False  # Signature verification failed


SECRET_KEY = "your_application_secret"
ACCESS_TOKEN_EXPIRE_MINUTES = 25
REFRESH_TOKEN_EXPIRE_DAYS = 7  # Refresh tokens valid for 7 days
CACHE_EXPIRATION_SECONDS = 600
jwt_cache = {}
public_key_cache = {}


def cache_jwt(token: str, payload: dict):
    """Caches the validated JWT with an expiration time."""
    jwt_cache[token] = {
        "payload": payload,
    }


def get_cached_jwt(token: str) -> dict:
    """Retrieves the cached JWT if it is still valid."""
    cached = jwt_cache.get(token, None)
    if cached and cached["payload"]["exp"] > datetime.now(tz=timezone.utc).timestamp():
        return cached["payload"]
    return None


def cache_public_key(kid: str, public_key):
    """Caches the public key for the given key id (kid)."""
    public_key_cache[kid] = public_key


def get_cached_public_key(kid: str):
    """Retrieves the cached public key for the given kid, if available."""
    return public_key_cache.get(kid, None)


def create_jwt(
    payload: Dict,
    secret: str = SECRET_KEY,
    algorithm: str = "HS256",
    exp_minutes: int = 30,
) -> str:
    """Creates a JWT with an expiration claim (exp)."""
    header = {"alg": algorithm, "typ": "JWT"}

    exp = datetime.now(tz=timezone.utc) + timedelta(minutes=exp_minutes)
    payload["iss"] = payload.get("iss", "self")
    payload["exp"] = int(exp.timestamp())  # Expiration time as Unix timestamp

    header_b64 = (
        base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    )
    payload_b64 = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )

    signature = hmac.new(
        secret.encode(), f"{header_b64}.{payload_b64}".encode(), hashlib.sha256
    ).digest()
    signature_b64 = base64.urlsafe_b64encode(signature).decode().rstrip("=")

    return f"{header_b64}.{payload_b64}.{signature_b64}"


def create_refresh_token() -> str:
    """Generates a secure random refresh token."""
    return secrets.token_urlsafe(32)


async def get_token_from_openid_provider(
    username: str, password: str, logger, endpoint_config: dict = None
) -> dict:
    """
    Gets a token from the given Keycloak or OpenID endpoint config.
    If no endpoint config is provided, it generates an internal JWT.
    """
    if not endpoint_config:
        # No endpoint config provided, create an internal JWT
        access_token_payload = {
            "username": username,
            "roles": ["user"],
            "permissions": ["read"],
            "iss": "self",
        }
        access_token = create_jwt(
            access_token_payload,
            secret=SECRET_KEY,
            exp_minutes=ACCESS_TOKEN_EXPIRE_MINUTES,
        )
        refresh_token = create_refresh_token()
        # TODO: store locally created refresh token + jwt in database
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # In seconds
            "refresh_expires_in": REFRESH_TOKEN_EXPIRE_DAYS
            * 24
            * 60
            * 60,  # In seconds,
            "token_type": "Bearer",
        }
    # If endpoint_config is provided, fetch the token from the provided endpoint
    data = {
        "client_id": endpoint_config.get("client_id"),
        "username": username,
        "password": password,
        "grant_type": "password",
        "client_secret": endpoint_config.get("client_secret"),
        "redirect_uri": endpoint_config.get("redirect_uri"),
    }

    encoded_data = urllib.parse.urlencode(data).encode()

    async def fetch_token():
        req = urllib.request.Request(
            endpoint_config["token_url"], data=encoded_data, method="POST"
        )
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        context = (
            ssl._create_unverified_context()
        )  # To avoid SSL verification for local testing
        with urllib.request.urlopen(req, context=context) as response:
            return json.loads(response.read().decode())

    return await fetch_token()


ph = argon2.PasswordHasher()


def create_password(plain_password, salt=None):
    # Generate a random salt if not provided
    if salt is None:
        salt = os.urandom(16)  # Generate a 16-byte random salt

    # Use the low-level hash_secret function with a custom salt
    hashed_password = ph.hash(
        plain_password.encode("utf-8"),  # The plain password
        salt=salt,  # The custom salt
    )
    return hashed_password, salt


def verify_password(hashed_password, plain_password, salt):
    # Hash the plain password with the provided salt
    new_hash = ph.hash(
        plain_password.encode("utf-8"),
        salt=salt,
    )

    # Verify if the newly hashed password matches the original hash
    return hashed_password == new_hash


async def get_token_from_local_system(
    password: str,
    user=None,
    tenant_secret: str = None,
    public_secret: str = None,
):
    """
    Here we check that the password matches the hash stored against the user with argon2
    Then we generate a JWT and return it using:
    public secret + tenant configuration secret + user secret
    """
    if not user:
        return {"error": "User not found"}, 404
    user_secret = user.token_secret
    salt = f"{public_secret}{tenant_secret}{user_secret}".encode("utf-8")

    if not verify_password(user.password_hash, password, salt):
        return {"error": "Invalid password"}, 401

    payload = {
        "username": user.username,
        "roles": user.roles,
        "permissions": user.permissions,
        "iss": "self",
    }
    header = {"alg": "HS256", "typ": "JWT"}
    header_bytes = orjson.dumps(header, separators=(",", ":"))
    payload_bytes = orjson.dumps(payload, separators=(",", ":"))

    signature = hmac.new(
        salt,
        f"{header_bytes}.{payload_bytes}".encode("utf-8"),
        hashlib.sha256,
    ).digest()
    signature_encoded = base64.urlsafe_b64encode(signature)
    jwt_token = f"{header_bytes}.{payload_bytes}.{signature_encoded}"

    return {"access_token": jwt_token, "token_type": "Bearer"}


async def fetch_openid_configuration(issuer_url: str):
    """Fetches OpenID configuration from the given issuer URL."""
    openid_config_url = f"{issuer_url.replace('locahost', 'localhost')}/.well-known/openid-configuration"
    return await asyncio.to_thread(_sync_fetch_openid_config, openid_config_url)


def _sync_fetch_openid_config(openid_config_url):
    with urllib.request.urlopen(
        openid_config_url, context=ssl._create_unverified_context()
    ) as response:
        return json.loads(response.read().decode())


async def fetch_public_key(jwks_uri: str, kid: str):
    """Fetches the public key for a given key id (kid) from the jwks_uri."""
    return await asyncio.to_thread(_sync_fetch_public_key, jwks_uri, kid)


def _sync_fetch_public_key(jwks_uri, kid):
    with urllib.request.urlopen(
        jwks_uri, context=ssl._create_unverified_context()
    ) as response:
        jwks = json.loads(response.read().decode())

    for key in jwks["keys"]:
        if key["kid"] == kid:
            return key

    raise ValueError("No matching key found")


def verify_exp(payload: Dict):
    """Checks if the token has expired by verifying the 'exp' claim."""
    exp = payload.get("exp", None)
    if not exp or datetime.now(tz=timezone.utc).timestamp() > exp:
        raise ValueError("Token has expired")


def verify_signature(header, payload, signature, secret):
    """Verifies the JWT signature using HMAC and the given secret."""
    signing_input = f"{header}.{payload}".encode("utf-8")
    calculated_signature = hmac.new(
        secret.encode("utf-8"), signing_input, hashlib.sha256
    ).digest()
    return hmac.compare_digest(base64url_decode(signature), calculated_signature)


def refresh_jwt_token(refresh_token: str, secret: str = SECRET_KEY) -> dict:
    """
    Verifies the refresh token and generates a new access token.
    If valid, it returns a new access token and the same refresh token.
    """
    # TODO: token is valid if it exists in the db against the user and is nto expired
    if len(refresh_token) != 43:  # Length of `secrets.token_urlsafe(32)` output
        raise ValueError("Invalid refresh token")

    payload = {
        "username": "user",
        "roles": ["user"],
        "permissions": ["read"],
        "iss": "self",
    }

    new_access_token = create_jwt(
        payload, secret=SECRET_KEY, exp_minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    return {
        "access_token": new_access_token,
        "refresh_token": refresh_token,  # Re-use the same refresh token
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # In seconds
    }


def base64url_decode(input):
    """Decodes base64url input, handling padding."""
    rem = len(input) % 4
    if rem > 0:
        input += "=" * (4 - rem)
    return base64.urlsafe_b64decode(input)


async def verify_jwt(token: str, secret: str = SECRET_KEY) -> dict:
    """
    Verifies the JWT signature.
    If the `iss` is "self", verify it locally using the internal secret.
    Otherwise, verify it using the issuer's public key.
    """
    cached_payload = get_cached_jwt(token)
    if cached_payload:
        return cached_payload

    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
        header = json.loads(base64url_decode(header_b64).decode("utf-8"))
        payload = json.loads(base64url_decode(payload_b64).decode("utf-8"))

        iss = payload.get("iss", None)
        if not iss:
            raise ValueError("JWT is missing 'iss' claim")

        db = Context.get_db()

        if iss == "self":
            if not verify_signature(
                header_b64, payload_b64, signature_b64, secret=secret
            ):
                raise ValueError("Invalid JWT signature for self-issued token")
            # TODO: also check if exp is hit
            # TODO: if a refresh token is given, generate and sign a new payload and return it
        else:
            openid_config = await fetch_openid_configuration(iss)
            jwks_uri = openid_config["jwks_uri"]

            kid = header.get("kid", None)
            if not kid:
                raise ValueError("JWT is missing 'kid' in header")
            public_key = get_cached_public_key(kid)
            if public_key is None:
                jwk = await fetch_public_key(jwks_uri, kid)
                public_key = load_rsa_public_key(jwk)
                cache_public_key(kid, public_key)

            if not verify_rs256_signature(
                header_b64, payload_b64, signature_b64, public_key
            ):
                raise ValueError("Invalid JWT signature for external token")

        cache_jwt(token, payload)

        return payload

    except Exception as e:
        raise ValueError(f"JWT verification failed: {str(e)}")
