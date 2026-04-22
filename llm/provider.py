import json
import os
from typing import Any, Iterator, Optional

import requests

from llm.groq_client import call_groq, get_groq_client


def _provider() -> str:
    return (os.getenv("LLM_PROVIDER", "groq") or "groq").strip().lower()


def _picoclaw_base_url() -> str:
    return (os.getenv("PICOCLAW_BASE_URL", "") or "").rstrip("/")


def call_llm(
    *,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.0,
    max_tokens: int = 2048,
    model: Optional[str] = None,
) -> str:
    """
    Provider abstraction.
    - groq: uses `llm.groq_client.call_groq`
    - picoclaw: uses OpenAI-compatible `/v1/chat/completions` by default
    """
    prov = _provider()
    if prov == "groq":
        return call_groq(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model,
        )

    if prov == "picoclaw":
        base = _picoclaw_base_url() or os.getenv("OPENAI_BASE_URL", "").rstrip("/")
        if not base:
            raise ValueError("PICOCLAW_BASE_URL (or OPENAI_BASE_URL) must be set for LLM_PROVIDER=picoclaw")

        api_key = os.getenv("PICOCLAW_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
        headers = {"Content-Type": "application/json"}
        # No-key-first mode: only send Authorization if provided.
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        if model is None:
            model = os.getenv("PICOCLAW_MODEL", "default")

        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": float(temperature),
            "max_tokens": int(max_tokens),
            "stream": False,
        }
        timeout = float(os.getenv("PICOCLAW_TIMEOUT_SEC", "60"))
        resp = requests.post(f"{base}/v1/chat/completions", headers=headers, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    raise ValueError(f"Unsupported LLM_PROVIDER: {prov}")


def stream_llm(
    *,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.0,
    max_tokens: int = 2048,
    model: Optional[str] = None,
) -> Iterator[str]:
    prov = _provider()
    if prov == "groq":
        # Use Groq python SDK streaming
        if model is None:
            model = os.getenv("GROQ_GENERATOR_MODEL", "llama-3.3-70b-versatile")
        client = get_groq_client()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=float(temperature),
            max_tokens=int(max_tokens),
            stream=True,
        )
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
        return

    if prov == "picoclaw":
        base = _picoclaw_base_url() or os.getenv("OPENAI_BASE_URL", "").rstrip("/")
        if not base:
            raise ValueError("PICOCLAW_BASE_URL (or OPENAI_BASE_URL) must be set for LLM_PROVIDER=picoclaw")
        api_key = os.getenv("PICOCLAW_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if model is None:
            model = os.getenv("PICOCLAW_MODEL", "default")

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": float(temperature),
            "max_tokens": int(max_tokens),
            "stream": True,
        }

        connect_timeout = float(os.getenv("STREAM_CONNECT_TIMEOUT_SEC", "10"))
        read_timeout = float(os.getenv("STREAM_READ_TIMEOUT_SEC", "120"))
        with requests.post(
            f"{base}/v1/chat/completions",
            headers=headers,
            json=payload,
            stream=True,
            timeout=(connect_timeout, read_timeout),
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                # OpenAI-compatible SSE: "data: {...}" and "data: [DONE]"
                if line.startswith("data:"):
                    data = line[len("data:") :].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                        delta = obj["choices"][0].get("delta", {}).get("content")
                        if delta:
                            yield str(delta)
                    except Exception:
                        continue
        return

    raise ValueError(f"Unsupported LLM_PROVIDER: {prov}")

