import base64
import hashlib
import hmac
import json
from typing import Dict, Optional

SECRET_KEY = "your-secret-key"  # Use a strong, secret key in production


def base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def base64url_decode(data: str) -> bytes:
    padded_data = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded_data.encode("utf-8"))


def create_jwt(
    payload: Dict[str, str], secret: str = SECRET_KEY, algorithm: str = "HS256"
) -> str:
    header = {"alg": algorithm, "typ": "JWT"}

    header_bytes = json.dumps(header, separators=(",", ":")).encode("utf-8")
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    header_encoded = base64url_encode(header_bytes)
    payload_encoded = base64url_encode(payload_bytes)

    signature = hmac.new(
        secret.encode("utf-8"),
        f"{header_encoded}.{payload_encoded}".encode("utf-8"),
        hashlib.sha256,
    ).digest()
    signature_encoded = base64url_encode(signature)

    jwt_token = f"{header_encoded}.{payload_encoded}.{signature_encoded}"
    return jwt_token


def verify_jwt(
    token: str, secret: str = SECRET_KEY, algorithm: str = "HS256"
) -> Optional[Dict[str, str]]:
    try:
        header_encoded, payload_encoded, signature_encoded = token.split(".")

        signature = hmac.new(
            secret.encode("utf-8"),
            f"{header_encoded}.{payload_encoded}".encode("utf-8"),
            hashlib.sha256,
        ).digest()
        expected_signature_encoded = base64url_encode(signature)

        if not hmac.compare_digest(signature_encoded, expected_signature_encoded):
            return None

        payload_bytes = base64url_decode(payload_encoded)
        payload = json.loads(payload_bytes.decode("utf-8"))

        return payload
    except Exception:
        return None
