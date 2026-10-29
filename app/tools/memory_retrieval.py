from typing import Any, Dict, Optional
from app.logging.audit_log import AuditLogger
from app.memory.database_operations import DatabaseOperations


def retrieve_learner_state(
    db: DatabaseOperations,
    logger: AuditLogger,
    learner_id: str,
    requesting_learner_id: Optional[str] = None,
    disable_retrieval: bool = False,
) -> Dict[str, Any]:
    if disable_retrieval:
        logger.log_event(
            learner_id,
            "MEMORY_READ",
            "retrieve_learner_state",
            "disabled_for_comparison",
            {"reason": "Diagnostic comparison with retrieval disabled"},
            memory_type="working_state",
        )
        return {
            "learner_id": learner_id,
            "current_profile": None,
            "active_plan": None,
            "active_task": None,
            "practice_sessions": [],
            "skills": [],
            "obstacles": [],
            "episode_summaries": [],
            "retrieval_disabled": True,
        }

    state = db.get_learner_state(learner_id, requesting_learner_id=requesting_learner_id or learner_id)
    logger.log_event(
        learner_id,
        "MEMORY_READ",
        "retrieve_learner_state",
        "success",
        {
            "has_profile": state["current_profile"] is not None,
            "profile_version": state["current_profile"]["version"] if state["current_profile"] else None,
            "active_plan_version": state["active_plan"]["version"] if state["active_plan"] else None,
            "session_count": len(state["practice_sessions"]),
            "episode_count": len(state.get("episode_summaries", [])),
        },
        memory_type="working_state",
    )
    return state