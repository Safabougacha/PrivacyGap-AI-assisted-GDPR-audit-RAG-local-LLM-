"""Access to the local vector database (ChromaDB), shared by ingest and retriever."""
import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

from src.config import CHROMA_DIR

COLLECTION = "legal_texts"


def get_client():
    # PersistentClient = the database is saved on disk in ./chroma_db
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def get_collection(client=None):
    client = client or get_client()
    return client.get_or_create_collection(
        name=COLLECTION,
        embedding_function=DefaultEmbeddingFunction(),  # all-MiniLM-L6-v2, local
        metadata={"hnsw:space": "cosine"},  # compare vectors by angle (meaning)
    )
