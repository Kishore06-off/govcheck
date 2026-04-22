import logging
import os
from functools import lru_cache

logger = logging.getLogger(__name__)

_encoding = None


def _get_encoding():
    """Lazy-load tiktoken; aligns chunk boundaries with real token counts."""
    global _encoding
    if _encoding is None:
        try:
            import tiktoken

            name = os.getenv("TIKTOKEN_ENCODING", "cl100k_base")
            _encoding = tiktoken.get_encoding(name)
        except Exception as e:
            logger.warning("tiktoken unavailable (%s); using character fallback", e)
            _encoding = False
    return _encoding

def _fast_estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4) if text and text.strip() else 0

@lru_cache(maxsize=max(256, int(os.getenv("TOKEN_COUNT_CACHE_SIZE", "20000"))))
def _count_tokens_cached(text: str) -> int:
    enc = _get_encoding()
    if enc is False:
        return _fast_estimate_tokens(text)
    try:
        n = len(enc.encode(text, disallowed_special=()))
        return n if n > 0 else 0
    except Exception as e:
        logger.debug("encode failed, fallback: %s", e)
        return _fast_estimate_tokens(text)


def count_tokens(text: str) -> int:
    """
    Token count for chunk sizing. Prefers tiktoken; falls back to len//4 if needed.
    """
    if not text or not text.strip():
        return 0
    # Fast mode for throughput-sensitive ingestion.
    if os.getenv("FAST_TOKEN_COUNT", "false").lower() in ("1", "true", "yes"):
        return _fast_estimate_tokens(text)
    return _count_tokens_cached(text)


def tiktoken_length(text: str) -> int:
    """
    LangChain length_function: must match count_tokens for consistent splits.
    """
    return count_tokens(text)