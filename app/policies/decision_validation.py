from typing import Any, Dict, List, Literal
from pydantic import BaseModel, Field
from app.memory.memory_validation import MemoryValidationError


AllowedDecision = Literal[
    "Continue",
    "advance",
    "reinforce",
    "simplify",
    "reschedule",
    "request clarification",
]


class DecisionProposal(BaseModel):
    decision: AllowedDecision = Field(
        description="Continue, advance, reinforce, simplify, reschedule, or request clarification."
    )
    recommended_task: str = Field(description="Next achievable task title and instructions.")
    reason: str = Field(description="Why this action is suitable based on history and evidence.")
    supporting_evidence: List[str] = Field(
        description="Relevant practice records, assessments, and resource references."
    )
    estimated_minutes: int = Field(description="Expected duration in minutes.")
    success_criteria: List[str] = Field(description="Measurable criteria the learner must demonstrate.")
    approval_required: bool = Field(default=False, description="Whether a change needs confirmation.")
    memory_changes: Dict[str, Any] = Field(
        default_factory=dict,
        description="Proposed profile, progress, or plan changes.",
    )


def validate_decision_proposal(
    proposal: DecisionProposal,
    current_profile: Dict[str, Any],
    active_plan: Dict[str, Any] | None,
) -> None:
    if not current_profile:
        raise MemoryValidationError("Cannot validate proposal without an active learner profile.")

    max_weekly_minutes = int(float(current_profile["hours_per_week"]) * 60)
    if proposal.estimated_minutes <= 0 or proposal.estimated_minutes > max_weekly_minutes:
        raise MemoryValidationError(
            f"Proposed task duration ({proposal.estimated_minutes} min) exceeds learner's available weekly time ({max_weekly_minutes} min)."
        )

    if proposal.decision != "request clarification":
        if not proposal.success_criteria:
            raise MemoryValidationError("Changed or assigned tasks must include explicit success_criteria.")
        if not proposal.reason or len(proposal.reason.strip()) < 5:
            raise MemoryValidationError("A supporting rationale is required for any task recommendation.")