import re
from typing import Any, Dict, Tuple


INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"grant\s+admin",
    r"override\s+policy",
    r"bypass\s+approval",
    r"delete\s+from\s+learners",
]


def detect_untrusted_instruction(text: str) -> bool:
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def check_approval_required(
    current_profile: Dict[str, Any],
    proposed_changes: Dict[str, Any],
    user_approved: bool = False,
) -> Tuple[bool, str]:
    """
    Learner-submitted availability adjustments can update profile versions directly,
    while changes to primary goal or target deadline require explicit confirmation.
    """
    if not proposed_changes:
        return False, "No profile constraints modified."

    new_goal = proposed_changes.get("goal")
    new_deadline = proposed_changes.get("deadline")

    if (new_goal and new_goal != current_profile["goal"]) or (
        new_deadline and new_deadline != current_profile["deadline"]
    ):
        if not user_approved:
            return True, "Changes to approved goal or target deadline require explicit confirmation."

    return False, "Within approved policy boundaries."