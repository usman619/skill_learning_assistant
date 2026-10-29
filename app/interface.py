import argparse
import json
import os
import sys
from dotenv import load_dotenv
from app.workflow_controller import WorkflowController

# ANSI color codes for formatted terminal output (G10)
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_MAGENTA = "\033[35m"
_BLUE = "\033[34m"


def _supports_color() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _c(color: str, text: str) -> str:
    return f"{color}{text}{_RESET}" if _supports_color() else text


def _print_section(title: str, color: str = _CYAN) -> None:
    print(f"\n{_c(color, _BOLD + '━' * 60)}")
    print(f"  {_c(color, _BOLD + title)}")
    print(f"{_c(color, _BOLD + '━' * 60)}")


def _print_kv(key: str, value: str, indent: int = 2) -> None:
    pad = " " * indent
    print(f"{pad}{_c(_DIM, key + ':')} {value}")


def _format_proposal(proposal: dict) -> None:
    decision = proposal.get("decision", "unknown")
    color_map = {
        "advance": _GREEN, "Continue": _GREEN, "reinforce": _YELLOW,
        "simplify": _YELLOW, "reschedule": _YELLOW, "request clarification": _RED,
    }
    dc = color_map.get(decision, _RESET)
    _print_section("Recommended Next Action", _MAGENTA)
    _print_kv("Decision", _c(dc, _BOLD + decision))
    _print_kv("Task", proposal.get("recommended_task", "—"))
    _print_kv("Reason", proposal.get("reason", "—"))
    _print_kv("Est. Minutes", str(proposal.get("estimated_minutes", "—")))
    if proposal.get("supporting_evidence"):
        print(f"  {_c(_DIM, 'Evidence:')}")
        for ev in proposal["supporting_evidence"]:
            print(f"    • {ev}")
    if proposal.get("success_criteria"):
        print(f"  {_c(_DIM, 'Success Criteria:')}")
        for sc in proposal["success_criteria"]:
            print(f"    ✓ {sc}")
    if proposal.get("approval_required"):
        print(f"  {_c(_RED, _BOLD + '⚠ Approval required before proceeding')}")


def _format_profile(profile: dict) -> None:
    _print_section("Learner Profile", _BLUE)
    _print_kv("Goal", profile.get("goal", "—"))
    _print_kv("Level", profile.get("current_level", "—"))
    _print_kv("Hours/Week", str(profile.get("hours_per_week", "—")))
    _print_kv("Deadline", profile.get("deadline", "—"))
    _print_kv("Version", str(profile.get("version", "—")))


def _format_assessment(assessment: dict) -> None:
    status = assessment.get("overall_status", "Unknown")
    color = _GREEN if status == "Demonstrated" else _YELLOW if status == "Partial" else _RED
    _print_section("Evidence Assessment", _YELLOW)
    _print_kv("Status", _c(color, _BOLD + status))
    _print_kv("Score", str(assessment.get("score", "—")))
    if assessment.get("demonstrated_skills"):
        print(f"  {_c(_DIM, 'Demonstrated:')}")
        for s in assessment["demonstrated_skills"]:
            print(f"    {_c(_GREEN, '✓')} {s}")
    if assessment.get("missing_gaps"):
        print(f"  {_c(_DIM, 'Gaps:')}")
        for g in assessment["missing_gaps"]:
            print(f"    {_c(_RED, '✗')} {g}")


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="D12 Skill Learning Accountability Assistant CLI")
    parser.add_argument("--db", default=os.getenv("D12_DB_PATH", "outputs/d12_assistant.db"), help="SQLite DB path")
    parser.add_argument("--json", action="store_true", help="Output raw JSON instead of formatted text")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. Onboard command
    p_onboard = subparsers.add_parser("onboard", help="Session 1: Onboard learner and generate initial plan")
    p_onboard.add_argument("--learner-id", default="learner_demo_01")
    p_onboard.add_argument("--goal", default="Learn Python data analysis")
    p_onboard.add_argument("--level", default="beginner")
    p_onboard.add_argument("--hours", type=float, default=4.0)
    p_onboard.add_argument("--deadline", default="2026-11-30")

    # 2. Submit practice / correction command
    p_submit = subparsers.add_parser("submit", help="Record practice outcome, evaluate evidence, and adapt plan")
    p_submit.add_argument("--learner-id", default="learner_demo_01")
    p_submit.add_argument("--outcome", choices=["completed", "partial", "missed"], required=True)
    p_submit.add_argument("--evidence", default="")
    p_submit.add_argument("--new-hours", type=float, default=None)
    p_submit.add_argument("--idempotency-key", required=True)

    # 3. Inspect state after restart command
    p_status = subparsers.add_parser("status", help="Recover and inspect persistent state from SQLite")
    p_status.add_argument("--learner-id", default="learner_demo_01")

    # 4. Export to Excel (G5/G6)
    p_export = subparsers.add_parser("export", help="Export learner data to an Excel workbook (read-only review)")
    p_export.add_argument("--learner-id", default="learner_demo_01")
    p_export.add_argument("--output", default="outputs/learner_report.xlsx", help="Output Excel file path")

    args = parser.parse_args()
    controller = WorkflowController(args.db)
    use_json = getattr(args, "json", False)

    if args.command == "onboard":
        res = controller.onboard_learner(
            learner_id=args.learner_id,
            goal=args.goal,
            current_level=args.level,
            hours_per_week=args.hours,
            deadline=args.deadline,
        )
        if use_json:
            print(json.dumps(res, indent=2))
        else:
            _format_profile(res["profile"])
            print(f"\n  {_c(_DIM, 'Resources found:')} {len(res.get('resources', []))}")
            for r in res.get("resources", []):
                print(f"    📚 {r['title']} — {_c(_DIM, r['url'])}")
            _format_proposal(res["proposal"])

    elif args.command == "submit":
        res = controller.submit_practice_and_adapt(
            learner_id=args.learner_id,
            outcome=args.outcome,
            evidence_submission=args.evidence,
            idempotency_key=args.idempotency_key,
            updated_hours_per_week=args.new_hours,
        )
        if use_json:
            print(json.dumps(res, indent=2))
        else:
            if res.get("blocked"):
                _print_section("🚫 Submission Blocked", _RED)
                _print_kv("Reason", res.get("reason", "Security policy violation"))
                _print_kv("Action", res.get("action", "Rejected"))
            elif res.get("approval_required"):
                _print_section("⚠ Approval Required", _YELLOW)
                _print_kv("Message", res.get("message", "—"))
            elif not res.get("state_recovered"):
                _print_section("State Not Recovered", _RED)
                _format_proposal(res["proposal"])
            else:
                if res.get("current_profile"):
                    _format_profile(res["current_profile"])
                if res.get("assessment"):
                    _format_assessment(res["assessment"])
                if res.get("practice_record", {}).get("duplicate_prevented"):
                    print(f"\n  {_c(_YELLOW, '⚠ Duplicate submission detected — no side effects')}")
                _format_proposal(res["proposal"])

    elif args.command == "status":
        state = controller.db.get_learner_state(args.learner_id)
        history = controller.db.get_profile_history(args.learner_id)
        episodes = controller.db.get_episode_summaries(args.learner_id)
        if use_json:
            print(json.dumps({"recovered_state": state, "profile_version_history": history, "episodes": episodes}, indent=2))
        else:
            _print_section("Recovered State", _CYAN)
            if state.get("current_profile"):
                _format_profile(state["current_profile"])
            if state.get("active_plan"):
                _print_kv("Active Plan", f"v{state['active_plan']['version']} — {state['active_plan']['goal']}")
            if state.get("active_task"):
                _print_kv("Active Task", state["active_task"]["title"][:80])
            _print_kv("Practice Sessions", str(len(state.get("practice_sessions", []))))
            _print_kv("Skills Tracked", str(len(state.get("skills", []))))
            _print_kv("Profile Versions", str(len(history)))
            if episodes:
                _print_section("Long-Term Memory (Episodes)", _MAGENTA)
                for ep in episodes[:10]:
                    print(f"  [{ep['episode_type']}] {ep['summary'][:90]}")

    elif args.command == "export":
        output_dir = os.path.dirname(args.output)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        path = controller.export_learner_report(args.learner_id, args.output)
        print(f"{_c(_GREEN, '✓')} Report exported to: {path}")
        print(f"  {_c(_DIM, 'Note: This is a read-only view. The SQLite database is the authoritative store.')}")


if __name__ == "__main__":
    main()