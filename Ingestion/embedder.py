from sentence_transformers import SentenceTransformer
import numpy as np


class TextEmbedder:
    _instance=None 

    @classmethod
    def get_model(cls):
        if cls._instance is None:
            cls._instance=SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        return cls._instance
    
    @classmethod
    def embed_text(cls,text: str)->list[float]:
        model=cls.get_model()
        vec=model.encode(text,normalize_embeddings=True)
        return vec.tolist()
    
    @classmethod
    def embed_batch(cls,texts: list[str])->np.ndarray:
        model=cls.get_model()
        return model.encode(texts, normalize_embeddings=True)