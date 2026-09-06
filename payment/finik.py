import base64
import json
import time
from urllib.parse import quote, unquote

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


def normalize_pem(value):
    return (value or "").replace("\\n", "\n").strip()


def _encode_uri_component(value):
    return quote(unquote(str(value)), safe=";/?:@&=+$,-_.!~*'()#")


def canonical_request_data(method, path, headers, query_params=None, body=None):
    normalized_headers = {str(key).lower(): value for key, value in headers.items()}
    host = normalized_headers.get("host")
    if not host:
        raise ValueError("Заголовок Host обязателен для подписи Finik.")

    header_parts = [f"host:{host}"]
    for key in sorted(key for key in normalized_headers if key.startswith("x-api-")):
        header_parts.append(f"{key}:{normalized_headers[key]}")

    parts = [method.lower(), unquote(path or ""), "&".join(header_parts)]
    if query_params:
        query = "&".join(
            f"{_encode_uri_component(key)}={_encode_uri_component(value if value is not None else '')}"
            for key, value in sorted(query_params.items())
        )
        if query:
            parts.append(query)

    if body:
        sorted_body = {key: body[key] for key in sorted(body)}
        parts.append(json.dumps(sorted_body, ensure_ascii=False, separators=(",", ":")))
    else:
        parts.append("")
    return "\n".join(parts).encode("utf-8")


def sign_request(method, path, headers, body, private_key_pem, query_params=None):
    private_key = serialization.load_pem_private_key(
        normalize_pem(private_key_pem).encode("utf-8"),
        password=None,
    )
    signature = private_key.sign(
        canonical_request_data(method, path, headers, query_params=query_params, body=body),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("ascii")


def verify_request_signature(method, path, headers, body, public_key_pem, signature, query_params=None):
    try:
        public_key = serialization.load_pem_public_key(normalize_pem(public_key_pem).encode("utf-8"))
        public_key.verify(
            base64.b64decode(signature, validate=True),
            canonical_request_data(method, path, headers, query_params=query_params, body=body),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except (InvalidSignature, ValueError, TypeError):
        return False
    return True


def current_timestamp_ms():
    return str(int(time.time() * 1000))


def timestamp_is_fresh(timestamp, tolerance_seconds):
    try:
        age_ms = abs(int(time.time() * 1000) - int(timestamp))
    except (TypeError, ValueError):
        return False
    return age_ms <= tolerance_seconds * 1000
