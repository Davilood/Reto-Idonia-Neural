from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.models.report import MagicLink


class WorkflowStep(BaseModel):
    key: str
    label: str
    status: str
    detail: str
    duration_ms: int
    started_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowResult(BaseModel):
    workflow_id: str
    status: str
    patient_dni: str
    patient_name: str
    mode: str
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = None
    steps: list[WorkflowStep] = Field(default_factory=list)
    idonia: dict[str, str] = Field(default_factory=dict)
    recog: dict[str, Any] = Field(default_factory=dict)
    magic_link: MagicLink | None = None
    output_pdf: Path | None = None
    debug: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def started(
        cls,
        workflow_id: str,
        patient_dni: str,
        patient_name: str,
        mode: str,
    ) -> "WorkflowResult":
        return cls(
            workflow_id=workflow_id,
            status="running",
            patient_dni=patient_dni,
            patient_name=patient_name,
            mode=mode,
            started_at=datetime.now(timezone.utc),
        )
