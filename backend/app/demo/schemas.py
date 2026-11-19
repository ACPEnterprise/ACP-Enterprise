from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DemoProvisionResponse(BaseModel):
    environment_id: UUID
    company_id: UUID
    branch_id: UUID
    generation: int
    action: str
    counts: dict[str, int]


class DemoScenarioResponse(BaseModel):
    code: str
    title: str
    position: int
    guided_steps: list[dict[str, object]]
    condition: dict[str, object]
    record_refs: dict[str, object]


class DemoFeedbackCreate(BaseModel):
    category: str
    page: str = Field(min_length=1, max_length=240)
    scenario_code: str | None = None
    comment: str = Field(min_length=1, max_length=4000)
    app_sha: str = Field(min_length=7, max_length=64)


class DemoFeedbackResponse(BaseModel):
    id: UUID
    category: str
    page: str
    scenario_code: str | None
    comment: str
    app_sha: str
    created_at: datetime
