import numpy as np
try:
    from Ingestion.embedder import TextEmbedder
except ModuleNotFoundError:
    from embedder import TextEmbedder

def cosine_similarity(vec_a: np.ndarray, matrix_b: np.ndarray) -> np.ndarray:
    return np.dot(matrix_b, vec_a)

def find_candidate_chunks(topic_vector: list[float], chunks: list[str], threshold=0.45):
    if not chunks:
        return []
        
    model = TextEmbedder.get_model()
    chunk_embeddings = model.encode(chunks, normalize_embeddings=True)
    scores = cosine_similarity(np.array(topic_vector), chunk_embeddings)
    
    candidates = []
    for idx, score in enumerate(scores):
        if score >= threshold:
            candidates.append({"chunk": chunks[idx], "score": float(score)})
            
    return sorted(candidates, key=lambda x: x["score"], reverse=True)
