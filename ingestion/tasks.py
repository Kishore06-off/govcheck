import gc
import os
import time
import concurrent.futures

from celery_app import celery_app
from job_status import set_status


@celery_app.task(name="ingestion.run_ingestion_pipeline")
def run_ingestion_pipeline(file_path: str, filename: str, job_id: str, user_id: str = "anonymous") -> dict:
    """
    Celery task: ingestion pipeline with explicit cleanup between stages
    to keep worker memory stable under load.
    """
    try:
        t0 = time.perf_counter()
        delta_enabled = os.getenv("DELTA_INGEST_ENABLED", "true").lower() in ("1", "true", "yes")
        if delta_enabled:
            try:
                from ingestion.delta_index import compute_source_fingerprint, lookup_fingerprint

                fp = compute_source_fingerprint(file_path, filename)
                prev = lookup_fingerprint(user_id, fp)
                if prev:
                    elapsed = {"total_s": round(time.perf_counter() - t0, 3)}
                    set_status(
                        job_id,
                        {
                            "status": "completed",
                            "progress": 100,
                            "message": f"Skipped re-ingestion (duplicate source). Reusing indexed content: {prev.get('source_name','source')}",
                            "timings": elapsed,
                            "skipped_duplicate": True,
                        },
                    )
                    return {"ok": True, "chunks": int(prev.get("chunks", 0) or 0), "timings": elapsed, "skipped_duplicate": True}
            except Exception:
                # Never fail ingestion due to delta check.
                pass

        set_status(job_id, {"status": "processing", "progress": 25, "message": "Extracting text..."})

        from ingestion.router import route_file

        blocks = route_file(file_path, "upload", "Unknown")
        if not blocks:
            msg = "No extractable content found in the source document."
            set_status(job_id, {"status": "error", "progress": 0, "message": msg})
            return {"ok": False, "error": msg}
        t_extract = time.perf_counter()
        del route_file
        if os.getenv("INGEST_GC_BETWEEN_STAGES", "true").lower() in ("1", "true", "yes"):
            gc.collect()

        set_status(job_id, {"status": "processing", "progress": 50, "message": "Chunking text..."})
        from chunking.chunker import process_blocks

        chunks = process_blocks(blocks)
        if not chunks:
            msg = "Document parsed, but no chunks were produced. Try a text-based PDF or enable OCR dependencies."
            set_status(job_id, {"status": "error", "progress": 0, "message": msg})
            return {"ok": False, "error": msg}
        t_chunk = time.perf_counter()
        del blocks
        if os.getenv("INGEST_GC_BETWEEN_STAGES", "true").lower() in ("1", "true", "yes"):
            gc.collect()

        for c in chunks:
            c["user_id"] = user_id

        set_status(job_id, {"status": "processing", "progress": 75, "message": "Classifying & Embedding..."})
        from classification.rule_classifier import classify_chunks
        from embedding.embedder import embed_chunks
        from vectorstore.chroma_store import upsert_chunks
        from retrieval.bm25_store import build_bm25_index

        classified = classify_chunks(chunks)
        if not classified:
            msg = "No classified chunks were produced from parsed content."
            set_status(job_id, {"status": "error", "progress": 0, "message": msg})
            return {"ok": False, "error": msg}
        t_classify = time.perf_counter()
        del chunks
        if os.getenv("INGEST_GC_BETWEEN_STAGES", "true").lower() in ("1", "true", "yes"):
            gc.collect()

        vectors = embed_chunks(classified)
        t_embed = time.perf_counter()
        # Parallelize index writes: vector upsert and BM25 build are independent.
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            fut_upsert = ex.submit(upsert_chunks, classified, vectors)
            fut_bm25 = ex.submit(build_bm25_index, classified, user_id)
            fut_upsert.result()
            fut_bm25.result()
        t_index = time.perf_counter()
        del vectors
        if os.getenv("INGEST_GC_BETWEEN_STAGES", "true").lower() in ("1", "true", "yes"):
            gc.collect()

        elapsed = {
            "extract_s": round(t_extract - t0, 3),
            "chunk_s": round(t_chunk - t_extract, 3),
            "classify_s": round(t_classify - t_chunk, 3),
            "embed_s": round(t_embed - t_classify, 3),
            "index_s": round(t_index - t_embed, 3),
            "total_s": round(t_index - t0, 3),
        }

        set_status(
            job_id,
            {
                "status": "completed",
                "progress": 100,
                "message": f"Successfully ingested {len(classified)} chunks",
                "timings": elapsed,
            },
        )
        if delta_enabled:
            try:
                from ingestion.delta_index import compute_source_fingerprint, record_fingerprint

                fp = compute_source_fingerprint(file_path, filename)
                if len(classified) > 0:
                    record_fingerprint(user_id, fp, len(classified), filename)
            except Exception:
                pass
        return {"ok": True, "chunks": len(classified), "timings": elapsed}
    except Exception as e:
        set_status(job_id, {"status": "error", "progress": 0, "message": str(e)})
        return {"ok": False, "error": str(e)}
    finally:
        # Best-effort cleanup of downloaded tmp files for URL ingestion
        try:
            if file_path and os.path.exists(file_path) and ("output" not in os.path.normpath(file_path)):
                os.remove(file_path)
        except Exception:
            pass
        gc.collect()

