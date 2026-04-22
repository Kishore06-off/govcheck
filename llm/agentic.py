import os
from typing import Optional, Tuple

from llm.provider import call_llm


def _agentic_enabled() -> bool:
    return (os.getenv("PICOCLAW_AGENTIC_ENABLED", "false") or "").lower() in ("1", "true", "yes")


def agentic_call(
    *,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int,
    model: Optional[str] = None,
    verify_fn=None,
) -> Tuple[str, dict]:
    """
    Minimal agentic loop (plan → execute → verify → optional revise) for PicoClaw mode.
    `verify_fn(answer) -> (ok: bool, feedback: str)` if provided.
    """
    if not _agentic_enabled():
        return call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model,
        ), {"agentic": False}

    plan_prompt = (
        "Create a short plan to answer the user using only the provided context.\n"
        "Do not answer yet. Return a numbered plan with 3-6 steps.\n\n"
        f"{user_prompt}"
    )
    plan = call_llm(
        system_prompt=system_prompt,
        user_prompt=plan_prompt,
        temperature=0.0,
        max_tokens=min(400, max_tokens),
        model=model,
    )

    exec_prompt = (
        "Follow the plan below strictly.\n"
        "If you cannot support the answer, abstain per instructions.\n\n"
        f"PLAN:\n{plan}\n\n"
        f"{user_prompt}"
    )
    answer = call_llm(
        system_prompt=system_prompt,
        user_prompt=exec_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        model=model,
    )

    meta = {"agentic": True, "plan": plan}
    if not verify_fn:
        return answer, meta

    ok, feedback = verify_fn(answer)
    meta["verify_ok"] = bool(ok)
    if ok:
        return answer, meta

    revise_enabled = (os.getenv("PICOCLAW_AGENTIC_REVISE", "true") or "").lower() in ("1", "true", "yes")
    if not revise_enabled:
        return answer, meta

    revise_prompt = (
        "Your previous answer failed verification.\n"
        f"Verification feedback:\n{feedback}\n\n"
        "Revise the answer to satisfy verification.\n"
        "If you still cannot, respond exactly: I cannot verify this from the provided documents.\n\n"
        f"{user_prompt}"
    )
    revised = call_llm(
        system_prompt=system_prompt,
        user_prompt=revise_prompt,
        temperature=0.0,
        max_tokens=max_tokens,
        model=model,
    )
    return revised, meta

