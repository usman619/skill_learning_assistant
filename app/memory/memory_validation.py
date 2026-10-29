from typing import Any, Dict


class MemoryValidationError(ValueError):
    """Raised when a proposed persistent state change violates deterministic rules."""


def validate_profile_values(goal: str, current_level: str, hours_per_week: float, deadline: str) -> None:
    if not goal or not goal.strip():
        raise MemoryValidationError("Learner goal must not be empty.")
    if hours_per_week <= 0 or hours_per_week > 80:
        raise MemoryValidationError(f"Invalid hours_per_week: {hours_per_week}. Must be between 0 and 80.")
    if not deadline or not deadline.strip():
        raise MemoryValidationError("Target deadline must be provided.")


def enforce_learner_isolation(requested_learner_id: str, record_learner_id: str) -> None:
    if requested_learner_id != record_learner_id:
        raise MemoryValidationError(
            f"Learner isolation violation: '{requested_learner_id}' cannot access '{record_learner_id}'."
        )


def validate_plan_version(expected_version: int, actual_current_version: int) -> None:
    if expected_version != actual_current_version:
        raise MemoryValidationError(
            f"Stale plan version conflict: expected {expected_version}, but active version is {actual_current_version}."
        )