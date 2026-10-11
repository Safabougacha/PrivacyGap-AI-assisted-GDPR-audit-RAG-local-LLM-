"""Step 2 - Retrieve the legal passages closest in meaning to a question."""
from src.config import TOP_K
from src.vectorstore import get_collection


def search(query: str, k: int = TOP_K) -> list[dict]:
    """Return the k most relevant chunks, best first.

    `distance` is the cosine distance: 0 = same meaning, higher = further away.
    """
    res = get_collection().query(query_texts=[query], n_results=k)
    return [
        {
            "id": res["ids"][0][i],
            "article": meta["article"],
            "title": meta["title"],
            "text": res["documents"][0][i],
            "distance": round(res["distances"][0][i], 3),
        }
        for i, meta in enumerate(res["metadatas"][0])
    ]
