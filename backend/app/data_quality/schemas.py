from pydantic import BaseModel, Field


class QualityRuleResponse(BaseModel):
    rule_id: str
    version: int
    domain: str
    state: str
    severity: str
    launch_impact: str
    explanation: str
    evidence_required: list[str]
    repair_owner: str
    automated_correction_prohibited: bool
    evidence_digest: str


class QualityIssueResponse(BaseModel):
    rule_id: str
    domain: str
    state: str
    severity: str
    launch_impact: str
    safe_record_identity: str
    explanation: str
    missing_or_conflicting_evidence: list[str]
    repair_owner: str
    evidence_digest: str
    blocks_new_operation: bool


class QualitySummaryResponse(BaseModel):
    catalog_version: str = "2026-09-01"
    catalog_digest: str
    company_id: str
    branch_scope: list[str]
    scanned_rules: int
    total_issues: int
    blocks_new_operation: int
    historical_only: int
    owner_review: int
    issues: list[QualityIssueResponse]
    limit: int = Field(ge=1, le=200)
    offset: int = Field(ge=0)
