from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
    confirmed_reference_no: Optional[str] = None
    confirmed_bank_name: Optional[str] = None
    confirmed_amount: Optional[Decimal] = None
    confirmed_issue_date: Optional[date] = None
    confirmed_maturity_date: Optional[date] = None
    mismatch_fields: list[str] = []

    @field_validator("mismatch_fields", mode="before")
    @classmethod
    def split_mismatches(cls, value):
        if isinstance(value, str):
            return [item for item in value.split(",") if item]
        return value


class DepositPage(BaseModel):
    items: list[DepositOut]
    total: int
    page: int
    page_size: int


class VerifyIn(BaseModel):
    # Bank-confirmed values. Leave a field out (null) if it was not checked.
    confirmed_reference_no: Optional[str] = None
    confirmed_bank_name: Optional[str] = None
    confirmed_amount: Optional[Decimal] = None
    confirmed_issue_date: Optional[date] = None
    confirmed_maturity_date: Optional[date] = None
    observations: str = ""


class RenewIn(DepositCreate):
    pass


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


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    deposit_id: int
    filename: str
    content_type: str
    size_bytes: int
    uploaded_by: str
    uploaded_at: datetime


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    deposit_id: int
    kind: str
    role: str
    message: str
    is_read: bool
    created_at: datetime


class CalendarEvent(BaseModel):
    on_date: date
    type: str
    deposit_id: int
    reference_no: str
    status: str
    renewal_due: bool
