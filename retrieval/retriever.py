import logging
import os
import time
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Weighted Reciprocal Rank Fusion (RRF) knobs
# SEARCH_WEIGHT_ALPHA controls dense vs sparse contribution (0..1).
# SEARCH_RRF_K controls rank smoothing (higher = flatter contributions).
ALPHA = float(os.getenv("SEARCH_WEIGHT_ALPHA", "0.7"))
RRF_K = float(os.getenv("SEARCH_RRF_K", "60"))

# Cross-encoder re-ranking disabled — requires a separate model download
# and blocks first query. Hybrid BM25+vector scoring is sufficient.
_reranker = None
_retrieve_cache: dict[tuple, tuple[float, list[dict]]] = {}

def _get_reranker():
    global _reranker
    if _reranker is not None:
        return _reranker

    enabled = os.getenv("RERANK_ENABLE", "false").lower() in ("1", "true", "yes")
    if not enabled:
        _reranker = False
        return None

    model_name = os.getenv("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
    try:
        from sentence_transformers import CrossEncoder
        logger.info(f"Loading cross-encoder reranker: {model_name}")
        _reranker = CrossEncoder(model_name)
        return _reranker
    except Exception as e:
        logger.warning(f"Failed to load reranker ({model_name}): {e}")
        _reranker = False
        return None


def normalize_scores(results: list[dict], score_key: str = "score", reverse: bool = False) -> list[dict]:
    """Min-Max normalization for scores to combine dense and sparse results."""
    if not results:
        return []
    
    scores = [r.get(score_key, 0) for r in results]
    min_score, max_score = min(scores), max(scores)
    
    for r in results:
        raw_score = r.get(score_key, 0)
        if max_score > min_score:
            r['normalized_score'] = (raw_score - min_score) / (max_score - min_score)
        else:
            r['normalized_score'] = 1.0 # If all scores are the same
            
        # Invert if it's a distance metric (like L2 in vector search)
        if reverse:
            r['normalized_score'] = 1.0 - r['normalized_score']
            
    return results

def _weighted_rrf_fuse(
    dense_results: list[dict],
    sparse_results: list[dict],
    top_k: int,
    alpha: float,
    k: float,
) -> list[dict]:
    """
    Weighted RRF fusion:
      score = alpha * 1/(k + rank_dense) + (1-alpha) * 1/(k + rank_sparse)
    where ranks start at 1. Missing list contributes 0.
    """
    dense_rank: dict[str, int] = {}
    sparse_rank: dict[str, int] = {}
    docs: dict[str, dict] = {}

    for i, r in enumerate(dense_results, 1):
        cid = r.get("chunk_id") or r.get("metadata", {}).get("chunk_id", "")
        if not cid:
            continue
        dense_rank[cid] = i
        docs.setdefault(cid, r)

    for i, r in enumerate(sparse_results, 1):
        cid = r.get("chunk_id") or r.get("metadata", {}).get("chunk_id", "")
        if not cid:
            continue
        sparse_rank[cid] = i
        docs.setdefault(cid, r)

    fused: list[dict] = []
    for cid, doc in docs.items():
        dr = dense_rank.get(cid)
        sr = sparse_rank.get(cid)
        score = 0.0
        if dr is not None:
            score += float(alpha) * (1.0 / (float(k) + float(dr)))
        if sr is not None:
            score += float(1.0 - alpha) * (1.0 / (float(k) + float(sr)))
        doc["hybrid_score"] = float(score)
        fused.append(doc)

    fused.sort(key=lambda x: x.get("hybrid_score", 0.0), reverse=True)
    return fused[:top_k]

def retrieve(
    query         : str,
    content_domain: str = None,
    document_type : str = None,
    source_format : str = None,
    top_k         : int = 5,
    user_id       : str = "anonymous"
) -> list[dict]:
    if not query or not query.strip():
        logger.warning("retrieve called with empty query")
        return []

    from embedding.embedder import embed_query
    from vectorstore.chroma_store import search
    from retrieval.bm25_store import search_bm25

    # Intercept generic checklist prompt and transform it to semantic keywords
    if "Strictly format as JSON" in query:
        search_query = "compliance requirement rule policy obligation procedure control standard"
    else:
        search_query = query

    cache_enabled = os.getenv("RETRIEVAL_CACHE_ENABLED", "false").lower() in ("1", "true", "yes")
    cache_ttl = float(os.getenv("RETRIEVAL_CACHE_TTL_SEC", "30"))
    cache_max = max(10, int(os.getenv("RETRIEVAL_CACHE_SIZE", "256")))
    cache_key = (
        search_query.strip().lower(),
        content_domain or "",
        document_type or "",
        source_format or "",
        int(top_k),
        user_id or "",
    )
    if cache_enabled:
        hit = _retrieve_cache.get(cache_key)
        now = time.time()
        if hit and (now - hit[0]) <= cache_ttl:
            return [dict(r) for r in hit[1]]

    # Step 1: Attempt embedding query (dense). If it fails, we still proceed with BM25.
    query_vector = None
    logger.info(f"Embedding query: '{search_query[:60]}'")
    try:
        query_vector = embed_query(search_query)
    except Exception as e:
        logger.error(f"Query embedding failed (dense will be skipped): {e}")

    # Step 2: Build metadata filters
    filters = {}
    if content_domain and content_domain != "all":
        filters["content_domain"] = content_domain
    if document_type and document_type != "all":
        filters["document_type"] = document_type
    if source_format and source_format != "all":
        filters["source_format"] = source_format
    if user_id:
        filters["user_id"] = user_id

    # We fetch more chunks to ensure good overlap for hybrid scoring
    fetch_k = max(top_k * 3, int(os.getenv("RETRIEVAL_FETCH_MULTIPLIER", "3")) * top_k)

    # Step 3: Search ChromaDB (Vector/Dense)
    semantic_results = []
    if query_vector is not None:
        try:
            semantic_results = search(query_vector=query_vector, filters=filters, top_k=fetch_k)
        except Exception as e:
            logger.error(f"Vector search failed (dense will be skipped): {e}")

    # Step 4: Search BM25 (Keyword/Sparse)
    keyword_results = search_bm25(search_query, top_k=fetch_k, user_id=user_id)
    if not semantic_results and not keyword_results:
        return []

    # Step 5: Weighted RRF fusion (more stable than score normalization)
    unique_results = _weighted_rrf_fuse(
        dense_results=semantic_results,
        sparse_results=keyword_results,
        top_k=max(top_k * int(os.getenv("RERANK_CANDIDATE_MULTIPLIER", "2")), top_k),
        alpha=ALPHA,
        k=RRF_K,
    )

    # Take the best candidates for Re-Ranking
    candidate_mult = int(os.getenv("RERANK_CANDIDATE_MULTIPLIER", "2"))
    candidates = unique_results[: max(top_k, top_k * candidate_mult)]

    # Step 6: Cross-Encoder Re-Ranking (Now optimally cached and scaled)
    reranker = _get_reranker()
    if reranker:
        try:
            pairs = [[search_query, doc.get("text", "")] for doc in candidates]        
            scores = reranker.predict(pairs)

            for doc, score in zip(candidates, scores):
                doc["score"] = float(score)

            candidates.sort(key=lambda x: x["score"], reverse=True)
            results = candidates[:top_k]
        except Exception as e:
            logger.warning(f"Re-ranking failed, falling back to hybrid weights: {e}")
            results = candidates[:top_k]
    else:
        results = candidates[:top_k]

    # Clean up sorting keys
    for r in results:
        r.pop("normalized_score", None)
        r.pop("distance", None)

    logger.info(f"Retrieved {len(results)} results using Weighted RRF (ALPHA={ALPHA}, K={RRF_K})")
    if cache_enabled:
        _retrieve_cache[cache_key] = (time.time(), [dict(r) for r in results])
        # Tiny LRU-ish pruning by oldest timestamps
        if len(_retrieve_cache) > cache_max:
            oldest = sorted(_retrieve_cache.items(), key=lambda kv: kv[1][0])[: len(_retrieve_cache) - cache_max]
            for k, _ in oldest:
                _retrieve_cache.pop(k, None)
    return results


def build_context_string(results: list[dict]) -> str:
    if not results:
        return ""

    context_parts = []
    for i, r in enumerate(results, 1):
        meta    = r.get("metadata", {})
        text    = r.get("text", "")
        # score could be hybrid_score or cross-encoder score
        score   = r.get("score", r.get("hybrid_score", 0))
        section = meta.get("section_heading") or meta.get("section_title", "â€”")
        source  = meta.get("source_url", "â€”")
        domain  = meta.get("content_domain", "â€”")
        page    = meta.get("page_number", 0)
        is_table = meta.get("is_table", 0)
        ents    = meta.get("named_entities", "")
        cid     = r.get("chunk_id") or meta.get("chunk_id", "")

        context_parts.append(
            f"[Chunk {i}]\n"
            f"chunk_id: {cid}\n"
            f"Section : {section}\n"
            f"Page    : {page}\n"
            f"Source  : {source}\n"
            f"Domain  : {domain}\n"
            f"Table   : {is_table}\n"
            f"Entities: {ents}\n"
            f"Score   : {score:.4f}\n"
            f"Text    : {text}\n"
        )

    return "\n".join(context_parts)


def retrieve_and_format(
    query         : str,
    content_domain: str = None,
    document_type : str = None,
    top_k         : int = 5,
    user_id       : str = "anonymous"
) -> tuple[list[dict], str]:
    results = retrieve(
        query          = query,
        content_domain = content_domain,
        document_type  = document_type,
        top_k          = top_k,
        user_id        = user_id
    )
    context = build_context_string(results)
    return results, context
