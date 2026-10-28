"""Password hashing, signed login tokens and role checks."""

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, Header, HTTPException

ROLES = {"INSTITUTION_USER", "REGULATOR_OFFICER", "APPROVING_AUTHORITY", "ADMIN"}
ALGORITHM = "HS256"
TOKEN_HOURS = 8
PBKDF2_ITERATIONS = 200_000


def _secret() -> str:
    # Must be set in the environment to a long random string. The server refuses to start without it.
    secret = os.getenv("AUTH_JWT_SECRET", "")
    if len(secret) < 32:
        raise RuntimeError(
            "AUTH_JWT_SECRET is missing or too short. Set it to a random string of at least 32 characters."
        )
    return secret


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if scheme != "pbkdf2":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), PBKDF2_ITERATIONS)
    return hmac.compare_digest(digest.hex(), digest_hex)


def create_token(username: str, full_name: str, role: str, institution_id: Optional[int]) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "name": full_name,
        "role": role,
        "inst": institution_id,
        "iat": now,
        "exp": now + timedelta(hours=TOKEN_HOURS),
    }
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


@dataclass(frozen=True)
class Actor:
    name: str  # username, used in the audit trail
    role: str
    institution_id: Optional[int]
    full_name: str = ""


def get_actor(authorization: str = Header(default="")) -> Actor:
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        raise HTTPException(status_code=401, detail="Please log in")
    try:
        claims = jwt.decode(authorization[len(prefix):], _secret(), algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Your session has expired. Please log in again.")
    role = claims.get("role")
    if role not in ROLES:
        raise HTTPException(status_code=401, detail="Invalid session")
    return Actor(
        name=claims["sub"],
        role=role,
        institution_id=claims.get("inst"),
        full_name=claims.get("name", ""),
    )


def require(*allowed: str):
    """ADMIN may do everything. Other roles must be listed. With no roles listed, only ADMIN may act."""

    def dependency(actor: Actor = Depends(get_actor)) -> Actor:
        if actor.role != "ADMIN" and actor.role not in allowed:
            raise HTTPException(status_code=403, detail=f"Role {actor.role} may not perform this action")
        return actor

    return dependency
