from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def clean_decimal(value: Any) -> Any:
    if value is None or isinstance(value, (int, float, Decimal)):
        return value
    if isinstance(value, str):
        s = value.strip().replace("₹", "").replace("Rs.", "").replace("Rs", "").replace("INR", "").strip()
        if not s:
            return None
        # Handle comma as decimal separator e.g. "10,000,00" or "10000,00"
        if "," in s and "." not in s:
            last_comma = s.rfind(",")
            dec_part = s[last_comma + 1 :]
            if len(dec_part) == 2:
                int_part = s[:last_comma].replace(",", "")
                s = f"{int_part}.{dec_part}"
            else:
                s = s.replace(",", "")
        else:
            s = s.replace(",", "")
        return Decimal(s)
    return value


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

    @field_validator("amount", mode="before")
    @classmethod
    def validate_amount(cls, value: Any) -> Any:
        return clean_decimal(value)

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

    @field_validator("confirmed_amount", mode="before")
    @classmethod
    def validate_confirmed_amount(cls, value: Any) -> Any:
        return clean_decimal(value)


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


# ---- FDR TRACE Schemas ----------------------------------------------------

class LineageLinkCreate(BaseModel):
    target_deposit_id: int
    relation_type: str = Field(pattern=r"^(ORIGINAL|RENEWAL|AUTO_RENEWAL|REPLACEMENT|SUPERSEDED|RELEASED_CLOSED)$")
    metadata: Optional[dict[str, Any]] = None


# ---- Release Readiness Schemas --------------------------------------------

class ReadinessPrereqNode(BaseModel):
    id: str
    category: str
    title: str
    is_mandatory: bool
    status: str
    explanation: str
    evidence: dict[str, Any]
    responsible_role: str
    next_action: str


class ReadinessOut(BaseModel):
    deposit_id: int
    release_request_id: Optional[int] = None
    overall_status: str
    is_ready_for_decision: bool
    completion_percentage: int
    total_prerequisites: int
    satisfied_count: int
    blocked_count: int
    missing_count: int
    pending_count: int
    blocking_reasons: list[str]
    next_actions: list[dict[str, Any]]
    nodes: list[ReadinessPrereqNode]
    edges: list[dict[str, str]]
    evaluated_at: str


# ---- Regulation Replay Schemas --------------------------------------------

class RegulationRuleCreate(BaseModel):
    rule_code: str = Field(min_length=3, max_length=64)
    version: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=3, max_length=255)
    description: str
    effective_from: date
    source_reference: str
    rule_spec: dict[str, Any]
    change_summary: str = ""


class RegulationRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rule_code: str
    version: str
    title: str
    description: str
    effective_from: date
    effective_to: Optional[date] = None
    status: str
    source_reference: str
    rule_spec_json: str
    change_summary: str
    author: str
    created_at: datetime
    published_at: Optional[datetime] = None


class ReplayRequest(BaseModel):
    target_rule_id: int


# ---- Cross-Record Integrity Schemas ---------------------------------------

class FindingActionCreate(BaseModel):
    action: str = Field(pattern=r"^(STATUS_CHANGE|ASSIGN|COMMENT|ESCALATE)$")
    notes: str = ""
    new_status: Optional[str] = Field(default=None, pattern=r"^(OPEN|UNDER_REVIEW|CONFIRMED_INCONSISTENCY|FALSE_POSITIVE|RESOLVED|ESCALATED)$")
    assignee: Optional[str] = None


# ============================================================================
# FEATURE 1: Smart Deadline & Expiry Alerts Schemas
# ============================================================================

class DeadlineItem(BaseModel):
    alert_id: str
    deposit_id: int
    reference_no: str
    institution_id: int
    institution_name: str
    institution_code: str
    deadline_type: str  # "MATURITY", "RENEWAL", "SCRUTINY_PENDING", "RELEASE_APPROVAL"
    deadline_label: str  # "FDR Maturity", "Renewal Required", "Scrutiny Pending", "Release Approval"
    deadline_date: date
    days_left: int  # Negative for overdue
    urgency: str  # "overdue", "due_soon", "upcoming", "completed"
    status: str  # FDR status: "ACTIVE", "EXPIRING", "MATURED", etc.
    amount: Decimal
    target_role: str  # "ALL", "REGULATOR_OFFICER", "APPROVING_AUTHORITY", "INSTITUTION_USER"
    is_my_action: bool
    url: str


class DeadlineSummary(BaseModel):
    overdue: int
    due_soon: int  # <= 15 or <= 7 days
    upcoming: int  # <= 30 days
    completed: int
    total: int


class DeadlinesResponse(BaseModel):
    items: list[DeadlineItem]
    summary: DeadlineSummary


# ============================================================================
# FEATURE 2: Explainable Document Verification Schemas
# ============================================================================

class ExtractedFieldMeta(BaseModel):
    value: Optional[str] = None
    status: str  # "Extracted", "Needs review", "Not detected"
    confidence: Optional[float] = None  # None unless genuine engine confidence
    evidence: Optional[str] = None  # Excerpt from document where value was found
    normalized: Optional[str] = None


class ExplainableExtraction(BaseModel):
    engine: str
    fields: dict[str, Optional[str]]
    structured: dict[str, ExtractedFieldMeta]
    warnings: list[str]


# ============================================================================
# FEATURE 3: Deficiency Report Generator Schemas
# ============================================================================

class DeficiencyItem(BaseModel):
    id: str
    category: str  # "FIELD_MISMATCH", "MISSING_DOCUMENT", "SCRUTINY_FLAG", "REGULATION_NON_COMPLIANCE"
    title: str
    field_name: Optional[str] = None
    submitted_value: Optional[str] = None
    verified_value: Optional[str] = None
    explanation: str
    required_action: str
    severity: str  # "CRITICAL", "HIGH", "MEDIUM"
    is_confirmed: bool = True


class DeficiencyReportPreview(BaseModel):
    deposit_id: int
    reference_no: str
    institution_name: str
    institution_code: str
    bank_name: str
    amount: Decimal
    issue_date: date
    maturity_date: date
    current_status: str
    has_deficiencies: bool
    summary_message: str
    deficiencies: list[DeficiencyItem]
    reviewer_comments: list[str]
    report_date: date


class DeficiencyReportGenerateIn(BaseModel):
    confirmed_deficiency_ids: list[str] = []
    additional_comments: Optional[str] = None
    custom_corrective_action: Optional[str] = None


