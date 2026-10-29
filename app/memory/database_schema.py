SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS learners (
    learner_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS learner_profiles (
    profile_id TEXT PRIMARY KEY,
    learner_id TEXT NOT NULL,
    goal TEXT NOT NULL,
    current_level TEXT NOT NULL,
    hours_per_week REAL NOT NULL,
    deadline TEXT NOT NULL,
    version INTEGER NOT NULL,
    is_current INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (learner_id) REFERENCES learners(learner_id)
);

CREATE TABLE IF NOT EXISTS skills (
    skill_id TEXT PRIMARY KEY,
    learner_id TEXT NOT NULL,
    skill_name TEXT NOT NULL,
    mastery_estimate REAL NOT NULL DEFAULT 0.0,
    evidence_summary TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (learner_id) REFERENCES learners(learner_id)
);

CREATE TABLE IF NOT EXISTS plans (
    plan_id TEXT PRIMARY KEY,
    learner_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    goal TEXT NOT NULL,
    status TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (learner_id) REFERENCES learners(learner_id)
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    title TEXT NOT NULL,
    acceptance_criteria TEXT NOT NULL,
    estimated_minutes INTEGER NOT NULL,
    due_date TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'assigned',
    FOREIGN KEY (plan_id) REFERENCES plans(plan_id)
);

CREATE TABLE IF NOT EXISTS practice_sessions (
    session_id TEXT PRIMARY KEY,
    learner_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    outcome TEXT NOT NULL,
    evidence_ref TEXT NOT NULL,
    assessment_status TEXT NOT NULL,
    assessment_summary TEXT NOT NULL,
    created_at TEXT NOT NULL,
    idempotency_key TEXT UNIQUE NOT NULL,
    FOREIGN KEY (learner_id) REFERENCES learners(learner_id),
    FOREIGN KEY (task_id) REFERENCES tasks(task_id)
);

CREATE TABLE IF NOT EXISTS resources (
    resource_id TEXT PRIMARY KEY,
    learner_id TEXT,
    topic TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    source TEXT NOT NULL,
    retrieved_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS obstacles (
    obstacle_id TEXT PRIMARY KEY,
    learner_id TEXT NOT NULL,
    description TEXT NOT NULL,
    frequency INTEGER NOT NULL DEFAULT 1,
    last_observed_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    FOREIGN KEY (learner_id) REFERENCES learners(learner_id)
);

CREATE TABLE IF NOT EXISTS event_logs (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    learner_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    outcome TEXT NOT NULL,
    memory_type TEXT NOT NULL DEFAULT 'operational',
    timestamp TEXT NOT NULL,
    details TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workflow_checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    learner_id TEXT NOT NULL,
    step_name TEXT NOT NULL,
    step TEXT,
    state_snapshot TEXT NOT NULL,
    checkpoint_data TEXT,
    status TEXT NOT NULL DEFAULT 'in_progress',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (learner_id) REFERENCES learners(learner_id)
);

CREATE TABLE IF NOT EXISTS episode_summaries (
    episode_id TEXT PRIMARY KEY,
    learner_id TEXT NOT NULL,
    episode_type TEXT NOT NULL,
    summary TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (learner_id) REFERENCES learners(learner_id)
);
"""