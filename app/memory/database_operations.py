import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.memory.memory_validation import (
    MemoryValidationError,
    enforce_learner_isolation,
    validate_plan_version,
    validate_profile_values,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DatabaseOperations:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def create_or_update_profile(
        self,
        learner_id: str,
        goal: str,
        current_level: str,
        hours_per_week: float,
        deadline: str,
    ) -> Dict[str, Any]:
        validate_profile_values(goal, current_level, hours_per_week, deadline)
        now = _now_iso()
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT learner_id FROM learners WHERE learner_id = ?", (learner_id,))
            if not cur.fetchone():
                cur.execute(
                    "INSERT INTO learners (learner_id, created_at, status) VALUES (?, ?, 'active')",
                    (learner_id, now),
                )

            cur.execute(
                "SELECT MAX(version) as max_v FROM learner_profiles WHERE learner_id = ?",
                (learner_id,),
            )
            row = cur.fetchone()
            next_version = (row["max_v"] or 0) + 1

            # Mark prior profiles as historical (is_current = 0) while preserving them
            cur.execute(
                "UPDATE learner_profiles SET is_current = 0 WHERE learner_id = ? AND is_current = 1",
                (learner_id,),
            )

            profile_id = f"prof_{uuid.uuid4().hex[:10]}"
            cur.execute(
                """
                INSERT INTO learner_profiles (
                    profile_id, learner_id, goal, current_level,
                    hours_per_week, deadline, version, is_current, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    profile_id,
                    learner_id,
                    goal,
                    current_level,
                    hours_per_week,
                    deadline,
                    next_version,
                    now,
                ),
            )
            conn.commit()
            return {
                "profile_id": profile_id,
                "learner_id": learner_id,
                "goal": goal,
                "current_level": current_level,
                "hours_per_week": hours_per_week,
                "deadline": deadline,
                "version": next_version,
                "is_current": True,
                "updated_at": now,
            }

    def get_current_profile(self, learner_id: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM learner_profiles
                WHERE learner_id = ? AND is_current = 1
                ORDER BY version DESC LIMIT 1
                """,
                (learner_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_profile_history(self, learner_id: str) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM learner_profiles WHERE learner_id = ? ORDER BY version ASC",
                (learner_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def create_or_revise_plan(
        self,
        learner_id: str,
        goal: str,
        reason: str,
        task_title: str,
        acceptance_criteria: List[str],
        estimated_minutes: int,
        due_date: str,
        priority: int = 1,
        expected_prior_version: Optional[int] = None,
    ) -> Dict[str, Any]:
        now = _now_iso()
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT plan_id, version FROM plans WHERE learner_id = ? AND status = 'active' ORDER BY version DESC LIMIT 1",
                (learner_id,),
            )
            active_plan = cur.fetchone()
            current_v = active_plan["version"] if active_plan else 0

            if expected_prior_version is not None:
                validate_plan_version(expected_prior_version, current_v)

            if active_plan:
                cur.execute(
                    "UPDATE plans SET status = 'superseded' WHERE plan_id = ?",
                    (active_plan["plan_id"],),
                )
                cur.execute(
                    "UPDATE tasks SET status = 'superseded' WHERE plan_id = ? AND status = 'assigned'",
                    (active_plan["plan_id"],),
                )

            new_version = current_v + 1
            plan_id = f"plan_{uuid.uuid4().hex[:10]}"
            task_id = f"task_{uuid.uuid4().hex[:10]}"

            cur.execute(
                """
                INSERT INTO plans (plan_id, learner_id, version, goal, status, reason, created_at)
                VALUES (?, ?, ?, ?, 'active', ?, ?)
                """,
                (plan_id, learner_id, new_version, goal, reason, now),
            )

            cur.execute(
                """
                INSERT INTO tasks (
                    task_id, plan_id, title, acceptance_criteria,
                    estimated_minutes, due_date, priority, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'assigned')
                """,
                (
                    task_id,
                    plan_id,
                    task_title,
                    json.dumps(acceptance_criteria),
                    estimated_minutes,
                    due_date,
                    priority,
                ),
            )
            conn.commit()
            return {
                "plan_id": plan_id,
                "learner_id": learner_id,
                "version": new_version,
                "goal": goal,
                "status": "active",
                "reason": reason,
                "active_task": {
                    "task_id": task_id,
                    "plan_id": plan_id,
                    "title": task_title,
                    "acceptance_criteria": acceptance_criteria,
                    "estimated_minutes": estimated_minutes,
                    "due_date": due_date,
                    "priority": priority,
                    "status": "assigned",
                },
            }

    def record_practice_session(
        self,
        learner_id: str,
        task_id: str,
        outcome: str,
        evidence_ref: str,
        assessment_status: str,
        assessment_summary: Dict[str, Any],
        idempotency_key: str,
    ) -> Dict[str, Any]:
        now = _now_iso()
        with self._conn() as conn:
            cur = conn.cursor()
            # Duplicate prevention via idempotency_key
            existing = cur.execute(
                "SELECT * FROM practice_sessions WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing:
                enforce_learner_isolation(learner_id, existing["learner_id"])
                result = dict(existing)
                result["duplicate_prevented"] = True
                result["assessment_summary"] = json.loads(result["assessment_summary"])
                return result

            # Confirm task belongs to learner's plan
            task_row = cur.execute(
                """
                SELECT t.task_id, p.learner_id FROM tasks t
                JOIN plans p ON t.plan_id = p.plan_id
                WHERE t.task_id = ?
                """,
                (task_id,),
            ).fetchone()
            if not task_row:
                raise MemoryValidationError(f"Task ID '{task_id}' does not exist.")
            enforce_learner_isolation(learner_id, task_row["learner_id"])

            session_id = f"sess_{uuid.uuid4().hex[:10]}"
            cur.execute(
                """
                INSERT INTO practice_sessions (
                    session_id, learner_id, task_id, outcome, evidence_ref,
                    assessment_status, assessment_summary, created_at, idempotency_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    learner_id,
                    task_id,
                    outcome,
                    evidence_ref,
                    assessment_status,
                    json.dumps(assessment_summary),
                    now,
                    idempotency_key,
                ),
            )

            if outcome == "completed" and assessment_status == "Demonstrated":
                cur.execute("UPDATE tasks SET status = 'completed' WHERE task_id = ?", (task_id,))
            conn.commit()
            return {
                "session_id": session_id,
                "learner_id": learner_id,
                "task_id": task_id,
                "outcome": outcome,
                "evidence_ref": evidence_ref,
                "assessment_status": assessment_status,
                "assessment_summary": assessment_summary,
                "created_at": now,
                "idempotency_key": idempotency_key,
                "duplicate_prevented": False,
            }

    def upsert_skill(
        self, learner_id: str, skill_name: str, mastery_estimate: float, evidence_summary: str
    ) -> None:
        now = _now_iso()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT skill_id FROM skills WHERE learner_id = ? AND skill_name = ?",
                (learner_id, skill_name),
            ).fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE skills SET mastery_estimate = ?, evidence_summary = ?, updated_at = ?
                    WHERE skill_id = ?
                    """,
                    (mastery_estimate, evidence_summary, now, row["skill_id"]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO skills (skill_id, learner_id, skill_name, mastery_estimate, evidence_summary, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (f"sk_{uuid.uuid4().hex[:10]}", learner_id, skill_name, mastery_estimate, evidence_summary, now),
                )
            conn.commit()

    def record_obstacle(self, learner_id: str, description: str) -> Dict[str, Any]:
        now = _now_iso()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM obstacles WHERE learner_id = ? AND description = ?",
                (learner_id, description),
            ).fetchone()
            if row:
                new_freq = row["frequency"] + 1
                conn.execute(
                    "UPDATE obstacles SET frequency = ?, last_observed_at = ? WHERE obstacle_id = ?",
                    (new_freq, now, row["obstacle_id"]),
                )
                obstacle_id = row["obstacle_id"]
            else:
                obstacle_id = f"obs_{uuid.uuid4().hex[:10]}"
                new_freq = 1
                conn.execute(
                    """
                    INSERT INTO obstacles (obstacle_id, learner_id, description, frequency, last_observed_at, status)
                    VALUES (?, ?, ?, 1, ?, 'active')
                    """,
                    (obstacle_id, learner_id, description, now),
                )
            conn.commit()
            return {"obstacle_id": obstacle_id, "description": description, "frequency": new_freq}

    def save_resource(
        self,
        topic: str,
        title: str,
        url: str,
        source: str,
        retrieved_at: str,
        learner_id: Optional[str] = None,
    ) -> str:
        res_id = f"res_{uuid.uuid4().hex[:10]}"
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO resources (resource_id, learner_id, topic, title, url, source, retrieved_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (res_id, learner_id, topic, title, url, source, retrieved_at),
            )
            conn.commit()
        return res_id

    # ── G1: Workflow checkpoint operations (crash / restart recovery) ──

    def save_checkpoint(
        self,
        learner_id: str,
        step_name: str,
        state_snapshot: Dict[str, Any],
        status: str = "in_progress",
    ) -> str:
        now = _now_iso()
        checkpoint_id = f"chk_{uuid.uuid4().hex[:10]}"
        snapshot_json = json.dumps(state_snapshot)
        with self._conn() as conn:
            # Ensure parent learner record exists to satisfy foreign key constraints
            conn.execute(
                "INSERT OR IGNORE INTO learners (learner_id, created_at, status) VALUES (?, ?, 'active')",
                (learner_id, now),
            )
            # Mark prior in-progress checkpoints for this learner+step as superseded
            conn.execute(
                """
                UPDATE workflow_checkpoints
                SET status = 'superseded', updated_at = ?
                WHERE learner_id = ? AND step_name = ? AND status = 'in_progress'
                """,
                (now, learner_id, step_name),
            )
            conn.execute(
                """
                INSERT INTO workflow_checkpoints (
                    checkpoint_id, learner_id, step_name, step,
                    state_snapshot, checkpoint_data, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    checkpoint_id,
                    learner_id,
                    step_name,
                    step_name,
                    snapshot_json,
                    snapshot_json,
                    status,
                    now,
                    now,
                ),
            )
            conn.commit()
        return checkpoint_id

    def complete_checkpoint(self, checkpoint_id: str) -> None:
        now = _now_iso()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT learner_id FROM workflow_checkpoints WHERE checkpoint_id = ?",
                (checkpoint_id,),
            ).fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE workflow_checkpoints
                    SET status = 'completed', updated_at = ?
                    WHERE learner_id = ? AND status = 'in_progress'
                    """,
                    (now, row["learner_id"]),
                )
            else:
                conn.execute(
                    "UPDATE workflow_checkpoints SET status = 'completed', updated_at = ? WHERE checkpoint_id = ?",
                    (now, checkpoint_id),
                )
            conn.commit()

    def get_latest_checkpoint(
        self, learner_id: str, key_or_step: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            if key_or_step:
                row = conn.execute(
                    """
                    SELECT * FROM workflow_checkpoints
                    WHERE learner_id = ? AND status = 'in_progress'
                      AND (step_name = ? OR checkpoint_id = ? OR step = ?)
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (learner_id, key_or_step, key_or_step, key_or_step),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT * FROM workflow_checkpoints
                    WHERE learner_id = ? AND status = 'in_progress'
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (learner_id,),
                ).fetchone()
            if row:
                result = dict(row)
                result["state_snapshot"] = json.loads(result["state_snapshot"])
                result["checkpoint_data"] = result["state_snapshot"]
                return result
            return None

    # ── G3: Episode summary operations (long-term memory) ──

    def add_episode_summary(
        self,
        learner_id: str,
        episode_type: str,
        summary: str,
        metadata: Optional[Dict[str, Any]] = None,
        source_plan_version: Optional[int] = None,
        source_session_id: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        now = _now_iso()
        episode_id = f"ep_{uuid.uuid4().hex[:10]}"
        meta = dict(metadata or {})
        if source_plan_version is not None:
            meta["source_plan_version"] = source_plan_version
        if source_session_id is not None:
            meta["source_session_id"] = source_session_id
        meta.update(kwargs)
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO episode_summaries (
                    episode_id, learner_id, episode_type, summary, metadata, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    episode_id,
                    learner_id,
                    episode_type,
                    summary,
                    json.dumps(meta),
                    now,
                ),
            )
            conn.commit()
        return episode_id

    def save_episode_summary(
        self,
        learner_id: str,
        episode_type: str,
        summary: str,
        metadata: Optional[Dict[str, Any]] = None,
        source_plan_version: Optional[int] = None,
        source_session_id: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        return self.add_episode_summary(
            learner_id=learner_id,
            episode_type=episode_type,
            summary=summary,
            metadata=metadata,
            source_plan_version=source_plan_version,
            source_session_id=source_session_id,
            **kwargs,
        )

    def get_episode_summaries(
        self, learner_id: str, episode_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            if episode_type:
                rows = conn.execute(
                    """
                    SELECT * FROM episode_summaries
                    WHERE learner_id = ? AND episode_type = ?
                    ORDER BY created_at DESC
                    """,
                    (learner_id, episode_type),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM episode_summaries WHERE learner_id = ? ORDER BY created_at DESC",
                    (learner_id,),
                ).fetchall()
            return [
                {**dict(r), "metadata": json.loads(r["metadata"])}
                for r in rows
            ]

    def get_learner_state(self, learner_id: str, requesting_learner_id: Optional[str] = None) -> Dict[str, Any]:
        if requesting_learner_id is not None:
            enforce_learner_isolation(requesting_learner_id, learner_id)

        with self._conn() as conn:
            profile = self.get_current_profile(learner_id)
            plan_row = conn.execute(
                "SELECT * FROM plans WHERE learner_id = ? AND status = 'active' ORDER BY version DESC LIMIT 1",
                (learner_id,),
            ).fetchone()
            active_plan = dict(plan_row) if plan_row else None

            active_task = None
            if active_plan:
                task_row = conn.execute(
                    "SELECT * FROM tasks WHERE plan_id = ? AND status = 'assigned' ORDER BY priority ASC LIMIT 1",
                    (active_plan["plan_id"],),
                ).fetchone()
                if task_row:
                    active_task = dict(task_row)
                    active_task["acceptance_criteria"] = json.loads(active_task["acceptance_criteria"])

            sessions = [
                {
                    **dict(r),
                    "assessment_summary": json.loads(r["assessment_summary"]),
                }
                for r in conn.execute(
                    "SELECT * FROM practice_sessions WHERE learner_id = ? ORDER BY created_at DESC",
                    (learner_id,),
                ).fetchall()
            ]

            skills = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM skills WHERE learner_id = ? ORDER BY updated_at DESC",
                    (learner_id,),
                ).fetchall()
            ]

            obstacles = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM obstacles WHERE learner_id = ? AND status = 'active'",
                    (learner_id,),
                ).fetchall()
            ]

            # G3: Include long-term episode summaries in learner state
            episode_summaries = self.get_episode_summaries(learner_id)

            # G1: Include any pending checkpoint for crash recovery
            pending_checkpoint = self.get_latest_checkpoint(learner_id)

            return {
                "learner_id": learner_id,
                "current_profile": profile,
                "active_plan": active_plan,
                "active_task": active_task,
                "practice_sessions": sessions,
                "skills": skills,
                "obstacles": obstacles,
                "episode_summaries": episode_summaries,
                "pending_checkpoint": pending_checkpoint,
            }