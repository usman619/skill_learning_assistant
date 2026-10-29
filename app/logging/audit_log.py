import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict


class AuditLogger:
    def __init__(self, db_path: str, run_id: str | None = None):
        self.db_path = db_path
        self.run_id = run_id or f"run_{uuid.uuid4().hex[:8]}"

    def log_event(
        self,
        learner_id: str,
        event_type: str,
        tool_name: str,
        outcome: str,
        details: Dict[str, Any],
        memory_type: str = "operational",
    ) -> str:
        """
        Log an auditable event to the event_logs table.

        memory_type values (G3 — distinguish source knowledge from long-term memory):
          - 'operational'    : routine workflow events (default)
          - 'working_state'  : mid-workflow checkpoints, current goal/plan context
          - 'long_term'      : approved milestones, commitments, episode summaries
          - 'source_knowledge': cached resources, document snapshots, indexes
        """
        event_id = f"evt_{uuid.uuid4().hex[:10]}"
        ts = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO event_logs (
                    event_id, run_id, learner_id, event_type,
                    tool_name, outcome, memory_type, timestamp, details
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    self.run_id,
                    learner_id,
                    event_type,
                    tool_name,
                    outcome,
                    memory_type,
                    ts,
                    json.dumps(details),
                ),
            )
            conn.commit()
        return event_id

    def get_event_log(self, learner_id: str, limit: int = 50) -> list[Dict[str, Any]]:
        """Retrieve recent event logs for a learner (useful for export/audit)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM event_logs
                WHERE learner_id = ?
                ORDER BY timestamp DESC LIMIT ?
                """,
                (learner_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]