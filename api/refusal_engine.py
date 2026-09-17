from __future__ import annotations

import re
import json
from pathlib import Path
from dataclasses import dataclass, asdict
from enum import Enum
from typing import List, Optional, Dict, Any


class Decision(str, Enum):
    ALLOW = "allow"
    REFUSE = "refuse"
    ALLOW_WITH_CONSTRAINTS = "allow_with_constraints"


@dataclass
class RefusalResult:
    decision: Decision
    reasons: List[str]
    matched_patterns: List[str]
    response: Optional[str] = None
    # You can log this for auditability:
    metadata: Optional[Dict[str, Any]] = None


# Get project root directory
PROJECT_ROOT = Path(__file__).parent.parent

# Cache for loaded responses
_refusal_responses_cache = None

def load_refusal_responses():
    """Load refusal responses from JSON file"""
    global _refusal_responses_cache
    if _refusal_responses_cache is not None:
        return _refusal_responses_cache
    
    try:
        candidate_paths = [
            PROJECT_ROOT / 'api' / 'config' / 'refusal_responses.json',
            PROJECT_ROOT / 'nutrifaq-dbase' / 'common' / 'refusal_responses.json',
        ]
        for path in candidate_paths:
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    _refusal_responses_cache = json.load(f)
                return _refusal_responses_cache

        raise FileNotFoundError(
            "refusal_responses.json not found in any expected location"
        )
    except Exception as e:
        raise Exception(f"Error loading refusal responses: {e}")

def get_refusal_response(response_type: str, language: str = "fr") -> str:
    """Get a refusal response by type and language"""
    responses = load_refusal_responses()
    lang_responses = responses.get(language, responses.get("fr", {}))
    return lang_responses.get(response_type, lang_responses.get("general_refusal", ""))

# Cache for loaded patterns
_refusal_patterns_cache = None

def load_refusal_patterns():
    """Load refusal patterns from JSON file"""
    global _refusal_patterns_cache
    if _refusal_patterns_cache is not None:
        return _refusal_patterns_cache
    
    try:
        with open(PROJECT_ROOT / 'api/config' / 'refusal_patterns.json', 'r', encoding='utf-8') as f:
            _refusal_patterns_cache = json.load(f)
        return _refusal_patterns_cache
    except Exception as e:
        raise Exception(f"Error loading refusal patterns: {e}")

def get_patterns_for_language(language: str = "fr") -> Dict[str, List[str]]:
    """Get patterns for a specific language"""
    all_patterns = load_refusal_patterns()
    return all_patterns.get(language, all_patterns.get("fr", {}))


def _match_patterns(text: str, patterns: List[str]) -> List[str]:
    hits = []
    for pat in patterns:
        if re.search(pat, text, flags=re.IGNORECASE):
            hits.append(pat)
    return hits


def refusal_engine(question: str, language: str = "fr") -> RefusalResult:
    """
    Decide whether to refuse before calling the LLM.
    - question/history/context are used ONLY for risk detection (not for generating advice).
    - language: "fr" or "en" for response language and pattern matching
    """
    print(f"[REFUSAL_ENGINE] Analyzing question (lang={language}): {question}...")
    combined = question.strip()

    matched: Dict[str, List[str]] = {}
    reasons: List[str] = []

    # Get patterns for the specified language
    patterns = get_patterns_for_language(language)

    # Evaluate categories
    for category, pats in patterns.items():
        hits = _match_patterns(combined, pats)
        if hits:
            matched[category] = hits
    
    if matched:
        print(f"[REFUSAL_ENGINE] Matched categories: {list(matched.keys())}")
        for category, patterns_matched in matched.items():
            print(f"[REFUSAL_ENGINE]   - {category}: {patterns_matched}")
    else:
        print(f"[REFUSAL_ENGINE] No risk patterns detected")

    # Decision logic (keep it deterministic and auditable)
    if "medication" in matched:
        print(f"[REFUSAL_ENGINE] ❌ REFUSED - Medication question detected")
        return RefusalResult(
            decision=Decision.REFUSE,
            reasons=["Medication / clinical compatibility question"],
            matched_patterns=matched["medication"],
            response=get_refusal_response("medication_refusal", language),
            metadata={"matched_categories": list(matched.keys())}
        )

    if "minor" in matched and ("personalized_request" in matched or "meal_plan" in matched):
        print(f"[REFUSAL_ENGINE] ❌ REFUSED - Minor with personalized request")
        return RefusalResult(
            decision=Decision.REFUSE,
            reasons=["Minor + weight/plan/personalized request"],
            matched_patterns=matched["minor"] + matched.get("personalized_request", []) + matched.get("meal_plan", []),
            response=get_refusal_response("minor_refusal", language),
            metadata={"matched_categories": list(matched.keys())}
        )

    if "possible_emergency" in matched:
        print(f"[REFUSAL_ENGINE] ❌ REFUSED - Possible emergency detected")
        return RefusalResult(
            decision=Decision.REFUSE,
            reasons=["Possible emergency / urgent situation"],
            matched_patterns=matched["possible_emergency"],
            response=get_refusal_response("emergency_refusal", language),
            metadata={"matched_categories": list(matched.keys())}
        )

    # Clinical conditions (diabetes, renal, etc.) => refuse to avoid clinical advice
    if "clinical_condition" in matched:
        print(f"[REFUSAL_ENGINE] ❌ REFUSED - Clinical condition mentioned")
        return RefusalResult(
            decision=Decision.REFUSE,
            reasons=["Clinical condition mentioned"],
            matched_patterns=matched["clinical_condition"],
            response=get_refusal_response("general_refusal", language),
            metadata={"matched_categories": list(matched.keys())}
        )

    # Meal plans or personal targets => refuse
    if "meal_plan" in matched:
        print(f"[REFUSAL_ENGINE] ❌ REFUSED - Meal plan request")
        return RefusalResult(
            decision=Decision.REFUSE,
            reasons=["Meal plan request"],
            matched_patterns=matched["meal_plan"],
            response=get_refusal_response("general_refusal", language),
            metadata={"matched_categories": list(matched.keys())}
        )

    if "personalized_request" in matched:
        print(f"[REFUSAL_ENGINE] ❌ REFUSED - Personalized request")
        return RefusalResult(
            decision=Decision.REFUSE,
            reasons=["Personalized recommendation request"],
            matched_patterns=matched["personalized_request"],
            response=get_refusal_response("general_refusal", language),
            metadata={"matched_categories": list(matched.keys())}
        )

    # Supplements are tricky: your prompt says never recommend specific supplements/dosages.
    # Here we choose ALLOW_WITH_CONSTRAINTS (let LLM explain general info but avoid recommendation).
    if "supplement" in matched:
        print(f"[REFUSAL_ENGINE] ⚠️ ALLOWED WITH CONSTRAINTS - Supplement mentioned")
        return RefusalResult(
            decision=Decision.ALLOW_WITH_CONSTRAINTS,
            reasons=["Supplement mentioned (allow general info only)"],
            matched_patterns=matched["supplement"],
            response=None,
            metadata={"matched_categories": list(matched.keys())}
        )

    # Numeric targets in the user text (optional policy choice)
    if "numeric_targets" in matched:
        print(f"[REFUSAL_ENGINE] ⚠️ ALLOWED WITH CONSTRAINTS - Numeric targets")
        return RefusalResult(
            decision=Decision.ALLOW_WITH_CONSTRAINTS,
            reasons=["Numeric targets mentioned (avoid numbers in reply)"],
            matched_patterns=matched["numeric_targets"],
            response=None,
            metadata={"matched_categories": list(matched.keys())}
        )

    print(f"[REFUSAL_ENGINE] ✅ ALLOWED - No risk detected")
    return RefusalResult(
        decision=Decision.ALLOW,
        reasons=[],
        matched_patterns=[],
        response=None,
        metadata={"matched_categories": list(matched.keys())}
    )


# Example integration point:
def validate_user_query(question: str, llm_call_fn, language: str = "fr"):
    """
    llm_call_fn should be your function that calls OpenAI with your system prompt.
    language: "fr" or "en" for response language
    """
    risk = refusal_engine(question=question, language=language)

    # If refuse, return template immediately (no LLM call)
    if risk.decision == Decision.REFUSE:
        return {
            "decision": risk.decision.value,
            "reasons": risk.reasons,
            "answer": risk.response,
            "audit": asdict(risk)
        }

    # If allow_with_constraints, call LLM but tighten constraints
    system_suffix = ""
    if risk.decision == Decision.ALLOW_WITH_CONSTRAINTS:
        system_suffix = (
            "\n\nADDITIONAL CONSTRAINTS:\n"
            "- Do not recommend any specific product/supplement/brand.\n"
            "- Do not provide dosages or numeric targets.\n"
            "- Keep it general and educational.\n"
        )


    return {
        "decision": risk.decision.value,
        "reasons": risk.reasons,
        "audit": asdict(risk)
    }
