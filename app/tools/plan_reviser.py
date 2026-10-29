from typing import Any, Dict, Optional
from app.logging.audit_log import AuditLogger
from app.memory.database_operations import DatabaseOperations
from app.policies.decision_validation import DecisionProposal, validate_decision_proposal


def revise_learning_plan(
    db: DatabaseOperations,
    logger: AuditLogger,
    learner_id: str,
    proposal: DecisionProposal,
    due_date: str = "2026-10-29",
    expected_prior_version: Optional[int] = None,
) -> Dict[str, Any]:
    current_profile = db.get_current_profile(learner_id)
    state = db.get_learner_state(learner_id)
    active_plan = state.get("active_plan")

    validate_decision_proposal(proposal, current_profile, active_plan)

    revised = db.create_or_revise_plan(
        learner_id=learner_id,
        goal=current_profile["goal"],
        reason=proposal.reason,
        task_title=proposal.recommended_task,
        acceptance_criteria=proposal.success_criteria,
        estimated_minutes=proposal.estimated_minutes,
        due_date=due_date,
        expected_prior_version=expected_prior_version,
    )

    # G3: Record plan revision as a long-term commitment episode
    db.save_episode_summary(
        learner_id=learner_id,
        episode_type="commitment",
        summary=(
            f"Plan v{revised['version']} — decision='{proposal.decision}', "
            f"task='{proposal.recommended_task[:80]}', "
            f"reason='{proposal.reason[:100]}'"
        ),
        source_plan_version=revised["version"],
    )

    logger.log_event(
        learner_id,
        "MEMORY_WRITE",
        "revise_learning_plan",
        "committed",
        {
            "plan_id": revised["plan_id"],
            "version": revised["version"],
            "decision": proposal.decision,
            "estimated_minutes": proposal.estimated_minutes,
        },
        memory_type="long_term",
    )
    return revised