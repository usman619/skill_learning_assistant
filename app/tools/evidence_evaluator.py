import re
from typing import Any, Dict, List
from app.logging.audit_log import AuditLogger
from app.policies.approval_rules import detect_untrusted_instruction


# G7: Robust regex patterns for evidence evaluation instead of fragile keyword matching
_EVIDENCE_PATTERNS = {
    "csv_load": re.compile(
        r"""
        (?:pd\.read_csv|pandas\.read_csv|read_csv)\s*\(  # function call
        |pd\.read_table|pd\.read_excel                    # alternative loaders
        |from\s+csv\s+import|csv\.reader                  # stdlib csv
        """,
        re.VERBOSE | re.IGNORECASE,
    ),
    "inspect_columns": re.compile(
        r"""
        \.columns|\.head\s*\(|\.info\s*\(|\.describe\s*\(
        |\.dtypes|\.shape|print\s*\(\s*df
        """,
        re.VERBOSE | re.IGNORECASE,
    ),
    "select_column": re.compile(
        r"""
        df\s*\[\s*['"]|df\s*\.\s*\w+         # df['col'] or df.col
        |\.loc\s*\[|\.iloc\s*\[               # loc/iloc indexing
        |\.select_dtypes                       # select by dtype
        """,
        re.VERBOSE | re.IGNORECASE,
    ),
    "calculate_mean": re.compile(
        r"""
        \.mean\s*\(|\.average\s*\(             # pandas/numpy mean
        |np\.mean\s*\(|numpy\.mean\s*\(        # numpy direct
        |statistics\.mean\s*\(                 # stdlib statistics
        |sum\s*\(.*\)\s*/\s*len\s*\(           # manual mean
        """,
        re.VERBOSE | re.IGNORECASE,
    ),
    "groupby": re.compile(
        r"""
        \.groupby\s*\(|\.pivot_table\s*\(
        |\.agg\s*\(|\.aggregate\s*\(
        """,
        re.VERBOSE | re.IGNORECASE,
    ),
}

# Negative patterns: these indicate the learner could NOT accomplish the task
_FAILURE_INDICATORS = re.compile(
    r"could\s+not|cannot|can't|didn'?t\s+(?:work|manage|figure|succeed)|"
    r"error(?:ed)?|traceback|exception|failed|unable\s+to",
    re.IGNORECASE,
)


def _match_criterion(criterion: str, clean_text: str) -> str:
    """Return 'Demonstrated' or 'Not demonstrated' for a single criterion."""
    c_low = criterion.lower()

    # Check for failure indicators near the criterion keywords
    has_failure = bool(_FAILURE_INDICATORS.search(clean_text))

    if "load" in c_low and "csv" in c_low:
        if _EVIDENCE_PATTERNS["csv_load"].search(clean_text):
            # If the learner loaded CSV but also reported failure, it's ambiguous
            if has_failure and "read_csv" in clean_text and "error" in clean_text.split("read_csv")[-1][:80]:
                return "Not demonstrated"
            return "Demonstrated"
        return "Not demonstrated"

    elif "inspect" in c_low or "columns" in c_low:
        if _EVIDENCE_PATTERNS["inspect_columns"].search(clean_text):
            return "Demonstrated"
        return "Not demonstrated"

    elif "select" in c_low and "column" in c_low:
        if _EVIDENCE_PATTERNS["select_column"].search(clean_text) and not has_failure:
            return "Demonstrated"
        return "Not demonstrated"

    elif "mean" in c_low:
        if _EVIDENCE_PATTERNS["calculate_mean"].search(clean_text) and not has_failure:
            return "Demonstrated"
        return "Not demonstrated"

    elif "group" in c_low:
        if _EVIDENCE_PATTERNS["groupby"].search(clean_text) and not has_failure:
            return "Demonstrated"
        return "Not demonstrated"

    else:
        # Generic criterion: require substantive content without failure indicators
        if len(clean_text) > 30 and not has_failure:
            return "Demonstrated"
        return "Unknown"


def evaluate_practice_evidence(
    logger: AuditLogger,
    learner_id: str,
    task_criteria: List[str],
    submission_text: str,
    outcome_reported: str,
) -> Dict[str, Any]:
    injection_detected = detect_untrusted_instruction(submission_text)
    clean_text = submission_text.lower().strip()

    if outcome_reported == "missed":
        result = {
            "criteria_results": {c: "Unknown" for c in task_criteria},
            "supporting_code_or_output": "Missing",
            "score": 0.0,
            "overall_status": "Missed",
            "missing_gaps": task_criteria,
            "demonstrated_skills": [],
            "injection_blocked": injection_detected,
        }
        logger.log_event(learner_id, "TOOL_CALL", "evaluate_practice_evidence", "missed_session", result)
        return result

    if not clean_text:
        result = {
            "criteria_results": {c: "Unknown" for c in task_criteria},
            "supporting_code_or_output": "Missing",
            "score": 0.0,
            "overall_status": "Unknown",
            "missing_gaps": task_criteria,
            "demonstrated_skills": [],
            "injection_blocked": injection_detected,
        }
        logger.log_event(learner_id, "TOOL_CALL", "evaluate_practice_evidence", "missing_evidence", result)
        return result

    # Check for conflicting claims (e.g., claims success without code/output or contradicts itself)
    if "completed everything" in clean_text and ("error" in clean_text or len(clean_text) < 35):
        result = {
            "criteria_results": {c: "Unknown" for c in task_criteria},
            "supporting_code_or_output": "Insufficient",
            "score": 0.0,
            "overall_status": "Conflicting/Insufficient",
            "missing_gaps": task_criteria,
            "demonstrated_skills": [],
            "injection_blocked": injection_detected,
        }
        logger.log_event(learner_id, "TOOL_CALL", "evaluate_practice_evidence", "conflicting_evidence", result)
        return result

    criteria_results: Dict[str, str] = {}
    demonstrated: List[str] = []
    missing_gaps: List[str] = []

    for criterion in task_criteria:
        status = _match_criterion(criterion, clean_text)
        criteria_results[criterion] = status
        if status == "Demonstrated":
            demonstrated.append(criterion)
        else:
            missing_gaps.append(criterion)

    applicable = len(task_criteria) if task_criteria else 1
    score = round(len(demonstrated) / applicable, 2)

    if len(demonstrated) == len(task_criteria):
        overall = "Demonstrated"
        support_status = "Sufficient"
    elif len(demonstrated) > 0:
        overall = "Partial"
        support_status = "Insufficient"
    else:
        overall = "Not demonstrated"
        support_status = "Insufficient"

    result = {
        "criteria_results": criteria_results,
        "supporting_code_or_output": support_status,
        "score": score,
        "overall_status": overall,
        "missing_gaps": missing_gaps,
        "demonstrated_skills": demonstrated,
        "injection_blocked": injection_detected,
    }
    logger.log_event(learner_id, "TOOL_CALL", "evaluate_practice_evidence", overall, result)
    return result