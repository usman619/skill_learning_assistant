from typing import Any, Dict
from app.logging.audit_log import AuditLogger
from app.memory.database_operations import DatabaseOperations


def record_practice_outcome(
    db: DatabaseOperations,
    logger: AuditLogger,
    learner_id: str,
    task_id: str,
    outcome: str,
    evidence_ref: str,
    assessment: Dict[str, Any],
    idempotency_key: str,
    obstacle_description: str | None = None,
) -> Dict[str, Any]:
    record = db.record_practice_session(
        learner_id=learner_id,
        task_id=task_id,
        outcome=outcome,
        evidence_ref=evidence_ref,
        assessment_status=assessment.get("overall_status", "Unknown"),
        assessment_summary=assessment,
        idempotency_key=idempotency_key,
    )

    if not record.get("duplicate_prevented"):
        for skill in assessment.get("demonstrated_skills", []):
            db.upsert_skill(learner_id, skill, 1.0, f"Demonstrated in session {record['session_id']}")
        for gap in assessment.get("missing_gaps", []):
            db.upsert_skill(learner_id, gap, 0.2, f"Gap identified in session {record['session_id']}")

        if obstacle_description:
            obs = db.record_obstacle(learner_id, obstacle_description)
            record["obstacle_recorded"] = obs

        # G3: Save long-term episode summary for this practice session
        episode_type = "milestone" if assessment.get("overall_status") == "Demonstrated" else "decision"
        summary = (
            f"Session outcome='{outcome}', status='{assessment.get('overall_status')}', "
            f"score={assessment.get('score', 0)}, "
            f"demonstrated={assessment.get('demonstrated_skills', [])}, "
            f"gaps={assessment.get('missing_gaps', [])}"
        )
        db.save_episode_summary(
            learner_id=learner_id,
            episode_type=episode_type,
            summary=summary,
            source_session_id=record["session_id"],
        )

    logger.log_event(
        learner_id,
        "MEMORY_WRITE",
        "record_practice_outcome",
        "duplicate_ignored" if record.get("duplicate_prevented") else "committed",
        {"session_id": record["session_id"], "idempotency_key": idempotency_key},
        memory_type="long_term",
    )
    return record