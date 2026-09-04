import time
import numpy as np
try:
    from Ingestion.embedder import TextEmbedder
except ModuleNotFoundError:
    from embedder import TextEmbedder


def cosine_similarity(vec_a: np.ndarray, matrix_b: np.ndarray) -> np.ndarray:
    return np.dot(matrix_b, vec_a)


def evaluate_chunk_similarities(topic_vector: list[float], chunks: list[str], threshold: float = 0.35) -> dict:
    """
    Computes cosine similarity between topic embedding vector and each email chunk.
    Returns rich diagnostics including all scores, max score, candidate matches, and execution duration.
    """
    start_time = time.perf_counter()
    if not chunks or topic_vector is None:
        return {
            "candidates": [],
            "all_scores": [],
            "max_score": 0.0,
            "min_score": 0.0,
            "passed_count": 0,
            "total_chunks": 0,
            "elapsed_ms": 0.0,
        }

    model = TextEmbedder.get_model()
    chunk_embeddings = model.encode(chunks, normalize_embeddings=True)
    scores = cosine_similarity(np.array(topic_vector), chunk_embeddings)

    all_scores = [round(float(s), 4) for s in scores]
    candidates = []
    for idx, score in enumerate(all_scores):
        if score >= threshold:
            candidates.append({
                "chunk_index": idx,
                "chunk": chunks[idx],
                "score": score
            })

    candidates = sorted(candidates, key=lambda x: x["score"], reverse=True)
    elapsed_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

    return {
        "candidates": candidates,
        "all_scores": all_scores,
        "max_score": max(all_scores) if all_scores else 0.0,
        "min_score": min(all_scores) if all_scores else 0.0,
        "passed_count": len(candidates),
        "total_chunks": len(chunks),
        "elapsed_ms": elapsed_ms,
    }


def find_candidate_chunks(topic_vector: list[float], chunks: list[str], threshold: float = 0.35):
    """
    Backward-compatible convenience wrapper returning candidate chunk list.
    """
    res = evaluate_chunk_similarities(topic_vector, chunks, threshold=threshold)
    return res["candidates"]
