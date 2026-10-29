import os
from typing import Any, Dict, List, Optional
from langchain_core.prompts import ChatPromptTemplate
from app.logging.audit_log import AuditLogger
from app.policies.decision_validation import DecisionProposal
from app.prompts import COORDINATOR_SYSTEM_PROMPT

from langchain_groq import ChatGroq


class AgentCoordinator:
    def __init__(self, logger: AuditLogger, model_name: Optional[str] = None):
        self.logger = logger
        self.model_name = model_name or os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
        self.api_key = os.getenv("GROQ_API_KEY", "").strip()
        self.llm_calls = 0

    def _can_use_live_groq(self) -> bool:
        return bool(self.api_key and self.api_key != "your_groq_api_key_here")

    def recommend_next_action(
        self,
        learner_id: str,
        state: Dict[str, Any],
        latest_assessment: Optional[Dict[str, Any]],
        resources: List[Dict[str, Any]],
        user_context: str = "",
    ) -> DecisionProposal:
        profile = state.get("current_profile")
        if not profile:
            return DecisionProposal(
                decision="request clarification",
                recommended_task="Please provide your baseline learning goal and weekly availability.",
                reason="No active profile could be retrieved from persistent memory.",
                supporting_evidence=["Persistent memory retrieval returned no profile."],
                estimated_minutes=15,
                success_criteria=["Submit learning goal and weekly study hours."],
                approval_required=False,
                memory_changes={},
            )

        hours = float(profile["hours_per_week"])
        budget_minutes = min(90, int(hours * 60 // 2))
        res_refs = [f"{r['title']} ({r['url']})" for r in resources[:2]]

        # Try live ChatGroq structured output first if configured
        if self._can_use_live_groq():
            try:

                llm = ChatGroq(
                    model=self.model_name,
                    api_key=self.api_key,
                    temperature=0.1,
                )
                structured_llm = llm.with_structured_output(DecisionProposal)
                prompt = ChatPromptTemplate.from_messages(
                    [
                        ("system", COORDINATOR_SYSTEM_PROMPT),
                        (
                            "human",
                            "Profile: {profile}\nActive Task: {active_task}\n"
                            "Latest Assessment: {assessment}\nObstacles: {obstacles}\n"
                            "Resources: {resources}\nUser Context: {user_context}\n"
                            "Produce the next DecisionProposal.",
                        ),
                    ]
                )
                chain = prompt | structured_llm
                self.llm_calls += 1
                proposal: DecisionProposal = chain.invoke(
                    {
                        "profile": profile,
                        "active_task": state.get("active_task"),
                        "assessment": latest_assessment,
                        "obstacles": state.get("obstacles", []),
                        "resources": res_refs,
                        "user_context": user_context,
                    }
                )
                # Ensure estimated_minutes respects current weekly hours
                if proposal.estimated_minutes > int(hours * 60):
                    proposal.estimated_minutes = budget_minutes
                self.logger.log_event(
                    learner_id,
                    "LLM_DECISION",
                    "ChatGroq",
                    "success",
                    {"model": self.model_name, "decision": proposal.decision},
                )
                return proposal
            except Exception as exc:
                self.logger.log_event(
                    learner_id,
                    "LLM_DECISION",
                    "ChatGroq",
                    "fallback_policy_engine",
                    {"model": self.model_name, "error": str(exc)},
                )

        # Deterministic evidence-informed policy engine (used when offline or if live model fails)
        return self._deterministic_policy_decision(profile, state, latest_assessment, res_refs, budget_minutes)

    def _deterministic_policy_decision(
        self,
        profile: Dict[str, Any],
        state: Dict[str, Any],
        assessment: Optional[Dict[str, Any]],
        res_refs: List[str],
        budget_minutes: int,
    ) -> DecisionProposal:
        obstacles = state.get("obstacles", [])
        sessions = state.get("practice_sessions", [])

        # Case 1: Initial onboarding plan
        if not sessions and assessment is None:
            return DecisionProposal(
                decision="Continue",
                recommended_task="Load a CSV file using pandas.read_csv(), inspect its columns, select a numeric column, and calculate its mean.",
                reason=f"Initial personalized task aligned with goal '{profile['goal']}' and {profile['hours_per_week']} hrs/week availability.",
                supporting_evidence=[f"Profile v{profile['version']} ({profile['hours_per_week']} hrs/week)"] + res_refs,
                estimated_minutes=budget_minutes,
                success_criteria=[
                    "Loads CSV successfully",
                    "Inspects columns",
                    "Selects intended numeric column",
                    "Calculates mean correctly",
                ],
                approval_required=False,
                memory_changes={"plan_action": "create_initial_plan"},
            )

        status = assessment.get("overall_status") if assessment else "Unknown"

        # Case 2: Conflicting or missing evidence
        if status in ("Conflicting/Insufficient", "Unknown"):
            return DecisionProposal(
                decision="request clarification",
                recommended_task="Please provide the exact Python snippet you ran and the console output so we can verify which criteria succeeded.",
                reason="Submitted evidence was missing or contained conflicting claims without supporting code or output.",
                supporting_evidence=[f"Assessment status: {status}"],
                estimated_minutes=20,
                success_criteria=["Provides supporting code or output"],
                approval_required=False,
                memory_changes={"provisional": True},
            )

        # Case 3: Missed session(s) / reduced availability
        if status == "Missed":
            repeated = any(o["frequency"] >= 2 for o in obstacles)
            decision_type = "simplify" if repeated else "reschedule"
            return DecisionProposal(
                decision=decision_type,
                recommended_task=(
                    f"Micro-practice ({budget_minutes} mins): Load 'sales.csv' with pandas, print df.columns, "
                    "and compute the mean of one numeric column."
                ),
                reason=(
                    f"Adapted workload after missed commitment and updated availability of "
                    f"{profile['hours_per_week']} hours/week (Profile v{profile['version']})."
                ),
                supporting_evidence=[
                    f"Missed session recorded",
                    f"Current Profile v{profile['version']}: {profile['hours_per_week']} hrs/week",
                ]
                + res_refs,
                estimated_minutes=budget_minutes,
                success_criteria=[
                    "Loads CSV successfully",
                    "Selects intended numeric column",
                    "Calculates mean correctly",
                ],
                approval_required=False,
                memory_changes={"plan_action": "reschedule_for_updated_constraints"},
            )

        # Case 4: Partial / weak evidence -> targeted reinforcement
        if status in ("Partial", "Not demonstrated"):
            gaps = assessment.get("missing_gaps", [])
            demonstrated = assessment.get("demonstrated_skills", [])
            return DecisionProposal(
                decision="reinforce",
                recommended_task=(
                    "Focused Exercise: Select the 'revenue' numeric column from your already-loaded DataFrame "
                    "(df['revenue']) and calculate its mean using df['revenue'].mean()."
                ),
                reason=(
                    f"Learner demonstrated {demonstrated} (score {assessment.get('score')}), "
                    f"but has remaining skill gaps in: {gaps}."
                ),
                supporting_evidence=[
                    f"Demonstrated: {', '.join(demonstrated) if demonstrated else 'None'}",
                    f"Missing criteria: {', '.join(gaps)}",
                ]
                + res_refs,
                estimated_minutes=min(45, budget_minutes),
                success_criteria=[
                    "Selects intended numeric column",
                    "Calculates mean correctly",
                ],
                approval_required=False,
                memory_changes={"plan_action": "targeted_gap_reinforcement"},
            )

        # Case 5: All criteria demonstrated -> advance
        return DecisionProposal(
            decision="advance",
            recommended_task="Group the dataset by category using df.groupby() and compare group means.",
            reason="All baseline CSV loading, column selection, and mean calculation criteria were demonstrated.",
            supporting_evidence=["All prior acceptance criteria demonstrated (score 1.0)"] + res_refs,
            estimated_minutes=budget_minutes,
            success_criteria=["Groups data by categorical column", "Calculates aggregated mean per group"],
            approval_required=False,
            memory_changes={"plan_action": "advance_curriculum"},
        )