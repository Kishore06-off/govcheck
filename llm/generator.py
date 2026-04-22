import json
import logging
import os
import re
from dotenv import load_dotenv

from llm.provider import call_llm, stream_llm
from llm.agentic import agentic_call
from llm.prompt_templates import (
    CHECKLIST_SYSTEM_PROMPT,
    CHECKLIST_USER_PROMPT
)

load_dotenv()

logger = logging.getLogger(__name__)

# â”€â”€ Allowed domains â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€      
VALID_DOMAINS = [
    "board_governance",
    "data_privacy",
    "risk_management",
    "audit_compliance",
    "shareholder_rights",
    "csr",
    "hr_policy",
    "financial_compliance",
]

_ABSTAIN = "I cannot verify this from the provided documents."


def _parse_json_response(raw: str) -> list[dict]:
    """
    Parse JSON array from LLM response.
    Handles cases where LLM adds extra text around JSON.
    """
    # Try direct parse first
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Try to extract JSON array from response
    try:
        start = raw.find("[")
        end   = raw.rfind("]") + 1
        if start != -1 and end > start:
            return json.loads(raw[start:end])
    except json.JSONDecodeError:
        pass

    logger.warning("Could not parse JSON from LLM response")
    return []

def _extract_chunk_ids_from_context(context_string: str) -> set[str]:
    # context has lines like "chunk_id: <id>"
    return set(re.findall(r"chunk_id:\s*([a-zA-Z0-9_\-]+)", context_string or ""))

def _has_valid_citations(answer_text: str, allowed_chunk_ids: set[str]) -> bool:
    cites = re.findall(r"\[chunk_id:([a-zA-Z0-9_\-]+)\]", answer_text or "")
    if not cites:
        return False
    return all(c in allowed_chunk_ids for c in cites)

def _filter_items_with_valid_chunk_id(items: list[dict], allowed_chunk_ids: set[str]) -> list[dict]:
    if not items:
        return []
    grounded = []
    for it in items:
        cid = str(it.get("chunk_id", "") or "")
        if cid and cid in allowed_chunk_ids:
            grounded.append(it)
    return grounded


def _validate_items(items: list[dict]) -> list[dict]:
    """
    Validate and clean checklist items.
    Ensures all required fields exist.
    """
    valid = []
    for item in items:
        if not isinstance(item, dict):
            continue

        text = item.get("item", "").strip()
        if not text:
            continue

        domain = item.get("domain", "").strip().lower()
        if domain not in VALID_DOMAINS:
            domain = "audit_compliance"

        # Normalize priority and action_type for cleaner UX and deterministic ranking downstream
        pr = str(item.get("priority", "") or "Medium").strip().lower()
        if pr in ("high", "h", "critical"):
            priority = "High"
        elif pr in ("low", "l", "minor"):
            priority = "Low"
        else:
            priority = "Medium"

        at = str(item.get("action_type", "") or "Process").strip().lower()
        action_type_map = {
            "policy": "Policy",
            "technical": "Technical",
            "tech": "Technical",
            "process": "Process",
            "training": "Training",
            "governance": "Process",
        }
        action_type = action_type_map.get(at, "Process")

        ev = str(item.get("evidence_required", "") or "").strip()
        if not ev or ev.lower() in ("n/a", "na", "none", "documentation"):
            ev = "Documentation, logs, or records demonstrating implementation."

        valid.append({
            "item"               : text,
            "domain"             : domain,
            "source_section"     : item.get("source_section", "—"),
            "page_number"        : int(item.get("page_number", 0) or 0),
            "source_quote"       : (item.get("source_quote", "") or "").strip(),
            "confidence"         : (item.get("confidence", "") or "").strip().lower() or "medium",
            "priority"           : priority,
            "action_type"        : action_type,
            "evidence_required"  : ev,
            "source_url"         : "",
            "chunk_id"           : str(item.get("chunk_id", "")),
            "compliance_framework": "",
            "verified"           : None,
            "verification_confidence": None,
            "verification_evidence": ""
        })

    return valid


def _enrich_with_metadata(
    items  : list[dict],
    results: list[dict]
) -> list[dict]:
    # Build lookup: chunk_id -> metadata
    chunk_map = {}
    for r in results:
        cid = r.get("chunk_id") or r.get("metadata", {}).get("chunk_id", "")
        meta = r.get("metadata", {})
        if cid:
            chunk_map[cid] = meta

    for item in items:
        cid = item.get("chunk_id", "")
        meta = chunk_map.get(cid)

        if meta:
            item["source_url"]           = meta.get("source_url","")
            item["compliance_framework"] = meta.get("compliance_framework","")
            if not item.get("page_number"):
                try:
                    item["page_number"] = int(meta.get("page_number", 0) or 0)
                except Exception:
                    item["page_number"] = 0
            if item.get("source_section") in ["—", "â€”", ""]:
                item["source_section"] = meta.get("section_heading") or meta.get("section_title", "—")
        else:
            source_section = item.get("source_section", "")
            for rcid, rmeta in chunk_map.items():
                sec = rmeta.get("section_heading") or rmeta.get("section_title", "")
                if sec and (source_section.lower() in sec.lower() or sec.lower() in source_section.lower()):
                    item["source_url"]           = rmeta.get("source_url","")
                    item["chunk_id"]             = rcid
                    item["compliance_framework"] = rmeta.get("compliance_framework","")
                    if not item.get("page_number"):
                        try:
                            item["page_number"] = int(rmeta.get("page_number", 0) or 0)
                        except Exception:
                            item["page_number"] = 0
                    break

    return items


_VERIFY_SYSTEM_PROMPT = """
You are a strict verifier for compliance requirements.

Rules:
1) Only mark supported=true if the requirement is directly supported by an exact quote in the provided chunks.
2) If you cannot find an exact supporting quote, supported=false.
3) Return ONLY JSON, no markdown, no commentary.

Return JSON object:
{
  "supported": true/false,
  "evidence": "<verbatim quote from chunks or 'none'>",
  "confidence": 0.0-1.0
}
""".strip()


def _verify_item(requirement_text: str, chunks_text: str) -> dict:
    user_prompt = (
        "Source chunks:\n"
        f"{chunks_text}\n\n"
        "Requirement:\n"
        f"{requirement_text}\n\n"
        "Answer with the JSON object only."
    )
    raw = call_llm(
        system_prompt=_VERIFY_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.0,
        max_tokens=500
    )
    try:
        return json.loads(raw)
    except Exception:
        # attempt to extract object
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(raw[start:end])
            except Exception:
                pass
    return {"supported": False, "evidence": "none", "confidence": 0.0}


def _verify_and_filter(items: list[dict], results: list[dict]) -> list[dict]:
    enabled = os.getenv("VERIFY_ENABLE", "true").lower() in ("1", "true", "yes")
    if not enabled or not items:
        return items

    min_conf = float(os.getenv("VERIFY_MIN_CONFIDENCE", "0.80"))
    # Build a chunk_id -> text map for verification quoting
    chunk_text = {}
    for r in results:
        cid = r.get("chunk_id") or r.get("metadata", {}).get("chunk_id", "")
        if cid:
            chunk_text[cid] = r.get("text", "")

    filtered: list[dict] = []
    for it in items:
        cid = it.get("chunk_id", "")
        # verify against its own chunk + a small neighborhood of top chunks
        focus = []
        if cid and cid in chunk_text:
            focus.append(chunk_text[cid])
        # add a couple more top chunks for safety
        for r in results[:3]:
            t = r.get("text", "")
            if t and t not in focus:
                focus.append(t)
        chunks_blob = "\n\n---\n\n".join(focus)[:12000]

        v = _verify_item(it.get("item", ""), chunks_blob)
        supported = bool(v.get("supported", False))
        conf = float(v.get("confidence", 0.0) or 0.0)
        evidence = str(v.get("evidence", "none") or "none").strip()

        it["verified"] = supported
        it["verification_confidence"] = conf
        it["verification_evidence"] = evidence if evidence.lower() != "none" else ""

        if supported and conf >= min_conf and evidence and evidence.lower() != "none":
            # If model didn't provide a quote during generation, use verifier evidence
            if not it.get("source_quote"):
                it["source_quote"] = evidence
            filtered.append(it)

    return filtered


def generate_checklist(
    context_string: str,
    results       : list[dict]
) -> list[dict]:
    """
    Generate a structured governance checklist
    from retrieved chunks using Groq API.
    """
    if not context_string or not context_string.strip():
        logger.warning(
            "generate_checklist called with empty context"
        )
        return []

    logger.info("Starting checklist generation via Groq API")

    user_prompt = CHECKLIST_USER_PROMPT.format(
        context=context_string
    )

    # ACCURACY FIX: Lowered temperature to 0.0 (from 0.3) to force purely deterministic, factual outputs.
    # High temperatures allow the model to get "creative", which leads to hallucinations in legal/compliance checks.
    logger.info("Attempt 1: Generating checklist with 0.0 temperature for maximum accuracy...")
    try:
        raw = call_llm(
            system_prompt = CHECKLIST_SYSTEM_PROMPT,
            user_prompt   = user_prompt,
            temperature   = 0.0,  # Zero temperature for deterministic facts
            max_tokens    = 3000  # Increased token limit so it doesn't arbitrarily cut off long checklists
        )
    except Exception as e:
        logger.error(f"Groq API call failed: {e}")
        return []

    items = _parse_json_response(raw)

    if not items:
        logger.warning("Attempt 1 failed. Retrying with stricter prompt...")
        strict_prompt = (
            user_prompt
            + "\n\nCRITICAL: Return ONLY a raw JSON array. "
            "Start with [ and end with ]. "
            "No markdown. No explanation. "
            "No text before or after the array."
        )
        try:
            raw = call_llm(
                system_prompt = CHECKLIST_SYSTEM_PROMPT,
                user_prompt   = strict_prompt,
                temperature   = 0.0,
                max_tokens    = 3000
            )
            items = _parse_json_response(raw)
        except Exception as e:
            logger.error(f"Retry failed: {e}")
            return []

    if not items:
        return []

    # Hard grounding: drop items whose chunk_id doesn't exist in retrieved context
    allowed_chunk_ids = _extract_chunk_ids_from_context(context_string)
    items = _filter_items_with_valid_chunk_id(items, allowed_chunk_ids)
    if not items:
        return []

    items = _validate_items(items)
    items = _enrich_with_metadata(items, results)
    items = _verify_and_filter(items, results)

    # Dedupe + deterministic ranking for audit-ready output
    seen = set()
    deduped: list[dict] = []
    for it in items:
        req_norm = " ".join(str(it.get("item", "") or "").lower().split())
        key = (req_norm, str(it.get("chunk_id", "") or ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(it)

    pr_rank = {"High": 0, "Medium": 1, "Low": 2}
    # Attach retrieval score if available in results metadata (used by UI + optional downstream)
    score_map = {}
    for r in results:
        cid = r.get("chunk_id") or r.get("metadata", {}).get("chunk_id", "")
        if cid:
            score_map[cid] = float(r.get("hybrid_score", r.get("score", 0.0)) or 0.0)
    for it in deduped:
        cid = str(it.get("chunk_id", "") or "")
        it["retrieval_score"] = float(score_map.get(cid, 0.0))

    deduped.sort(
        key=lambda x: (
            pr_rank.get(str(x.get("priority", "Medium")), 1),
            -float(x.get("retrieval_score", 0.0) or 0.0),
        )
    )

    cap = int(os.getenv("CHECKLIST_MAX_ITEMS", "120"))
    items = deduped[: max(0, cap)]
    
    return items


def generate_answer(
    query  : str,
    context: str
) -> str:
    from llm.prompt_templates import (
        ANSWER_SYSTEM_PROMPT,
        ANSWER_USER_PROMPT
    )

    if not query or not context:
        return "Insufficient context to answer this question."

    user_prompt = ANSWER_USER_PROMPT.format(
        query   = query,
        context = context
    )

    try:
        allowed_chunk_ids = _extract_chunk_ids_from_context(context)

        def _verify(answer_text: str):
            ok = _has_valid_citations(answer_text, allowed_chunk_ids)
            feedback = "Answer must include valid citations like [chunk_id:<id>] matching context chunk_ids."
            return ok, feedback

        # Optional agentic loop is only enabled by env flags (primarily for PicoClaw)
        answer, _meta = agentic_call(
            system_prompt=ANSWER_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.0,
            max_tokens=1500,
            verify_fn=_verify,
        )
        if not _has_valid_citations(answer, allowed_chunk_ids):
            return _ABSTAIN
        return answer
    except Exception as e:
        logger.error(f"Answer generation failed: {e}")
        return f"Could not generate answer: {e}"

def stream_answer(
    query  : str,
    context: str
):
    from llm.prompt_templates import (
        ANSWER_SYSTEM_PROMPT,
        ANSWER_USER_PROMPT
    )
    if not query or not context:
        yield "Insufficient context to answer this question."
        return

    user_prompt = ANSWER_USER_PROMPT.format(
        query   = query,
        context = context
    )
    
    try:
        for token in stream_llm(
            system_prompt=ANSWER_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.0,
            max_tokens=1500,
        ):
            yield token
    except Exception as e:
        logger.error(f"Answer stream failed: {e}")
        yield f"Could not generate answer stream: {e}"
