#!/usr/bin/env python3
"""JWT token generator for WebChat API tests and contract fuzzing.

Generates HS256 JWT tokens conforming to WebChat SOA specifications without
requiring external third-party dependencies (pure standard library).
"""

import argparse
import base64
import hashlib
import hmac
import json
import sys
import time
import uuid

# Default values matching docker-compose.yml and service settings
DEFAULT_WEBCHAT_JWT_SECRET = "dev-only-change-me"
DEFAULT_SERVICE_JWT_SECRET = "dev-only-service-secret"
DEFAULT_WEBCHAT_ISSUER = "webchat-identity"
DEFAULT_WEBCHAT_AUDIENCE = "webchat"
DEFAULT_IDENTITY_AUDIENCE = "identity-internal"
DEFAULT_SOCIAL_AUDIENCE = "social-internal"


def _b64url_encode(data: bytes) -> str:
    """Encode bytes using URL-safe base64 without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def create_hs256_jwt(payload: dict, secret: str) -> str:
    """Create an HMAC-SHA256 signed JWT string using standard library."""
    header = {"alg": "HS256", "typ": "JWT"}
    header_json = json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")

    encoded_header = _b64url_encode(header_json)
    encoded_payload = _b64url_encode(payload_json)

    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    encoded_signature = _b64url_encode(signature)

    return f"{encoded_header}.{encoded_payload}.{encoded_signature}"


def generate_user_token(
    user_id: str | None = None,
    username: str = "fuzz_user",
    secret: str = DEFAULT_WEBCHAT_JWT_SECRET,
    issuer: str = DEFAULT_WEBCHAT_ISSUER,
    audience: str = DEFAULT_WEBCHAT_AUDIENCE,
    ttl_seconds: int = 86400,
) -> str:
    """Generate a regular user bearer token (aud=webchat)."""
    now = int(time.time())
    sub = user_id or str(uuid.UUID("11111111-1111-4111-8111-111111111111"))
    payload = {
        "sub": sub,
        "username": username,
        "aud": audience,
        "iss": issuer,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return create_hs256_jwt(payload, secret)


def generate_identity_service_token(
    secret: str = DEFAULT_SERVICE_JWT_SECRET,
    issuer: str = "webchat-social",
    audience: str = DEFAULT_IDENTITY_AUDIENCE,
    sub: str = "social",
    ttl_seconds: int = 86400,
) -> str:
    """Generate a service token for Identity internal endpoints (aud=identity-internal, sub=social)."""
    now = int(time.time())
    payload = {
        "sub": sub,
        "aud": audience,
        "iss": issuer,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return create_hs256_jwt(payload, secret)


def generate_social_service_token(
    secret: str = DEFAULT_SERVICE_JWT_SECRET,
    issuer: str = "webchat-chat",
    audience: str = DEFAULT_SOCIAL_AUDIENCE,
    sub: str = "chat",
    ttl_seconds: int = 86400,
) -> str:
    """Generate a service token for Social internal endpoints (aud=social-internal, sub=chat)."""
    now = int(time.time())
    payload = {
        "sub": sub,
        "aud": audience,
        "iss": issuer,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return create_hs256_jwt(payload, secret)


def main():
    parser = argparse.ArgumentParser(description="Generate JWT tokens for WebChat API test harnesses")
    parser.add_argument(
        "--type",
        choices=["user", "identity-service", "social-service", "custom"],
        default="user",
        help="Token persona type (default: user)",
    )
    parser.add_argument("--sub", help="Subject claim (user UUID or service name)")
    parser.add_argument("--username", default="fuzz_user", help="Username claim (for user tokens)")
    parser.add_argument("--aud", help="Audience claim")
    parser.add_argument("--iss", help="Issuer claim")
    parser.add_argument("--secret", help="HMAC SHA256 secret key")
    parser.add_argument("--ttl", type=int, default=86400, help="Token validity in seconds (default: 86400)")

    args = parser.parse_args()

    if args.type == "user":
        token = generate_user_token(
            user_id=args.sub,
            username=args.username,
            secret=args.secret or DEFAULT_WEBCHAT_JWT_SECRET,
            issuer=args.iss or DEFAULT_WEBCHAT_ISSUER,
            audience=args.aud or DEFAULT_WEBCHAT_AUDIENCE,
            ttl_seconds=args.ttl,
        )
    elif args.type == "identity-service":
        token = generate_identity_service_token(
            secret=args.secret or DEFAULT_SERVICE_JWT_SECRET,
            issuer=args.iss or "webchat-social",
            audience=args.aud or DEFAULT_IDENTITY_AUDIENCE,
            sub=args.sub or "social",
            ttl_seconds=args.ttl,
        )
    elif args.type == "social-service":
        token = generate_social_service_token(
            secret=args.secret or DEFAULT_SERVICE_JWT_SECRET,
            issuer=args.iss or "webchat-chat",
            audience=args.aud or DEFAULT_SOCIAL_AUDIENCE,
            sub=args.sub or "chat",
            ttl_seconds=args.ttl,
        )
    elif args.type == "custom":
        if not args.sub or not args.aud or not args.secret:
            print("ERROR: --sub, --aud, and --secret are required for custom tokens", file=sys.stderr)
            sys.exit(1)
        now = int(time.time())
        payload = {
            "sub": args.sub,
            "aud": args.aud,
            "iss": args.iss or DEFAULT_WEBCHAT_ISSUER,
            "iat": now,
            "exp": now + args.ttl,
        }
        if args.username:
            payload["username"] = args.username
        token = create_hs256_jwt(payload, args.secret)

    print(token)


if __name__ == "__main__":
    main()
