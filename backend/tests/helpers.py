from typing import Optional

from app.auth import create_token


def hdr(role: str, user: str = "tester", inst: Optional[int] = None) -> dict:
    """Authorization header with a real signed token for the given role."""
    token = create_token(user, user, role, inst)
    return {"Authorization": f"Bearer {token}"}
