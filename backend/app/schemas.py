from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class InstitutionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=50)


class InstitutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str


class DepositCreate(BaseModel):
    institution_id: int
    reference_no: str = Field(min_length=1, max_length=100)
    bank_name: str = Field(min_length=1, max_length=255)
    amount: Decimal = Field(gt=0)
    issue_date: date
    maturity_date: date

    @model_validator(mode="after")
    def maturity_after_issue(self) -> "DepositCreate":
        if self.maturity_date <= self.issue_date:
            raise ValueError("maturity_date must be after issue_date")
        return self


class DepositOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    institution_id: int
    reference_no: str
    bank_name: str
    amount: Decimal
    issue_date: date
    maturity_date: date
    status: str
    previous_deposit_id: Optional[int]


class DepositPage(BaseModel):
    items: list[DepositOut]
    total: int
    page: int
    page_size: int


class VerifyIn(BaseModel):
    # Amount independently confirmed by the bank or the officer. None means "no discrepancy check, accept as submitted".
    confirmed_amount: Optional[Decimal] = None
    observations: str = ""


class ReleaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    deposit_id: int
    status: str
    status_before: str
    requested_by: str
    decided_by: Optional[str]
    remarks: str


class ReleaseDecision(BaseModel):
    approve: bool
    remarks: str = ""


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    action: str
    actor: str
    detail: str
    at: datetime
