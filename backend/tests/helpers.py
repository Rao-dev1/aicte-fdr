from typing import Optional

from app.auth import create_token


def hdr(role: str, user: str = "tester", inst: Optional[int] = None) -> dict:
    """Authorization header with a real signed token for the given role."""
    token = create_token(user, user, role, inst)
    return {"Authorization": f"Bearer {token}"}


def create_deposit_payload(
    inst_id: int = 1,
    ref: str = "FDR-001",
    amount: float = 100000.0,
    issue_date: str = "2024-01-01",
    maturity_date: str = "2027-01-01",
) -> dict:
    return {
        "institution_id": inst_id,
        "reference_no": ref,
        "bank_name": "State Bank of India",
        "amount": f"{amount:.2f}",
        "issue_date": issue_date,
        "maturity_date": maturity_date,
    }
