#!/usr/bin/env bash
set -e

export PYTHONPATH=.
export D12_DB_PATH="outputs/demonstration_logs/demo_session.db"
rm -f "$D12_DB_PATH"

echo "=== SESSION 1: Onboarding and Initial Plan (4 hrs/week) ==="
python3 -m app.interface --db "$D12_DB_PATH" --json onboard \
  --learner-id "learner_demo_01" \
  --goal "Learn Python data analysis" \
  --level "beginner" \
  --hours 4.0 \
  --deadline "2026-11-30" > outputs/demonstration_logs/session1_output.json

echo "=== SESSION 2: Missed Practice & Profile Correction (4 hrs -> 2 hrs/week) ==="
python3 -m app.interface --db "$D12_DB_PATH" --json submit \
  --learner-id "learner_demo_01" \
  --outcome "missed" \
  --evidence "I missed the practice session because I had less time than expected. I can now study only two hours per week." \
  --new-hours 2.0 \
  --idempotency-key "demo_sess2_001" > outputs/demonstration_logs/session2_output.json

echo "=== PROCESS TERMINATED: Restarting fresh Python process to verify SQLite recovery ==="
python3 -m app.interface --db "$D12_DB_PATH" --json status \
  --learner-id "learner_demo_01" > outputs/demonstration_logs/restart_status.json

echo "=== SESSION 3: Partial Evidence (Loads CSV, cannot calculate mean) and Targeted Adaptation ==="
python3 -m app.interface --db "$D12_DB_PATH" --json submit \
  --learner-id "learner_demo_01" \
  --outcome "partial" \
  --evidence "import pandas as pd; df = pd.read_csv('sales.csv'); print(df.columns) # I could not calculate the mean of the selected column" \
  --idempotency-key "demo_sess3_001" > outputs/demonstration_logs/session3_output.json

echo "=== EXPORT: Generating Excel report (read-only review backed by SQLite) ==="
python3 -m app.interface --db "$D12_DB_PATH" export \
  --learner-id "learner_demo_01" \
  --output "outputs/demonstration_logs/learner_report.xlsx"

echo "=== Running Test Scenarios (T01-T12) & Memory Comparisons (M01-M03) ==="
python3 -m pytest tests/test_scenarios.py -v
echo "Demo and evaluation complete. Logs written to outputs/."