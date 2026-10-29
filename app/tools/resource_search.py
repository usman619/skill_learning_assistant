import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List
from tavily import TavilyClient

from app.logging.audit_log import AuditLogger
from app.memory.database_operations import DatabaseOperations
from app.policies.approval_rules import detect_untrusted_instruction


def search_learning_resources(
    db: DatabaseOperations,
    logger: AuditLogger,
    learner_id: str,
    skill: str,
    topic: str,
    level: str = "beginner",
    catalogue_path: str = "data/resource_catalogue.json",
    simulate_failure: bool = False,
) -> List[Dict[str, Any]]:
    now = datetime.now(timezone.utc).isoformat()
    results: List[Dict[str, Any]] = []

    try:
        if simulate_failure:
            raise RuntimeError("Simulated external search API timeout.")

        tavily_key = os.getenv("TAVILY_API_KEY", "").strip()
        if tavily_key and tavily_key != "your_optional_tavily_api_key_here":

            client = TavilyClient(api_key=tavily_key)
            resp = client.search(query=f"{skill} {topic} {level} tutorial official docs", max_results=3)
            for item in resp.get("results", []):
                title = item.get("title", "Resource")
                if detect_untrusted_instruction(title):
                    title = "[SANITIZED RESOURCE TITLE]"
                entry = {
                    "title": title,
                    "url": item.get("url", ""),
                    "source": "tavily_live",
                    "relevance": "high",
                    "retrieved_at": now,
                    "is_cached": False,
                }
                # G4: Associate resource with learner
                db.save_resource(topic, entry["title"], entry["url"], entry["source"], now, learner_id=learner_id)
                results.append(entry)

        if not results:
            raise RuntimeError("Live search unavailable or unconfigured; using local catalogue fallback.")

        logger.log_event(
            learner_id, "TOOL_CALL", "search_learning_resources", "success_live",
            {"count": len(results)},
            memory_type="source_knowledge",
        )
        return results

    except Exception as exc:
        # Fallback to cached local resources and label them as cached
        if os.path.exists(catalogue_path):
            with open(catalogue_path, "r", encoding="utf-8") as f:
                catalogue = json.load(f)
            for item in catalogue:
                if detect_untrusted_instruction(item.get("title", "")):
                    continue
                entry = {
                    "title": item["title"],
                    "url": item["url"],
                    "source": item.get("source", "local_catalogue (cached)"),
                    "relevance": "high (cached fallback)",
                    "retrieved_at": now,
                    "is_cached": True,
                }
                # G4: Associate resource with learner
                db.save_resource(topic, entry["title"], entry["url"], entry["source"], now, learner_id=learner_id)
                results.append(entry)

        logger.log_event(
            learner_id,
            "TOOL_CALL",
            "search_learning_resources",
            "fallback_cached",
            {"error": str(exc), "cached_count": len(results)},
            memory_type="source_knowledge",
        )
        return results