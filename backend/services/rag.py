import os
import threading
import uuid
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, Filter,
    FieldCondition, MatchValue
)
from groq import Groq
from utils.document_loader import load_all_documents

QDRANT_PATH = os.getenv("QDRANT_PATH", "./qdrant_db")
DRAFTS_DATA_PATH = os.getenv("DRAFTS_DATA_PATH", "./data/drafts")
COLLECTION_NAME = "nyayasetu_legal_docs"
VECTOR_SIZE = 384

_qdrant_client = None
_qdrant_lock = threading.Lock()
_embedding_model = None
_embedding_lock = threading.Lock()

def get_qdrant():
    # Double-checked locking: S2's parallel citation checking calls this from multiple
    # threads at once (asyncio.to_thread). Without the lock, concurrent first-callers
    # each try to open the local embedded Qdrant path simultaneously, which fails with
    # "Storage folder already accessed by another instance" (Qdrant's embedded mode
    # holds an exclusive file lock) -- caught by search_judgments' try/except and
    # silently misreported as "Not found in indexed corpus". This was caught in S2
    # end-to-end testing, not theoretical.
    global _qdrant_client
    if _qdrant_client is None:
        with _qdrant_lock:
            if _qdrant_client is None:
                qdrant_url = os.getenv("QDRANT_URL")
                qdrant_api_key = os.getenv("QDRANT_API_KEY")

                if qdrant_url and qdrant_api_key and not qdrant_url.startswith("your_"):
                    try:
                        client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key, timeout=10)
                        client.get_collections()
                        _qdrant_client = client
                    except Exception:
                        print("[RAG] Cloud Qdrant connection failed. Falling back to local embedded Qdrant.")
                        _qdrant_client = QdrantClient(path=QDRANT_PATH)
                else:
                    _qdrant_client = QdrantClient(path=QDRANT_PATH)
    return _qdrant_client


import hashlib
import time

def get_embeddings(texts: list, batch_size: int = 32) -> list:
    from fastembed import TextEmbedding
    global _embedding_model
    if _embedding_model is None:
        with _embedding_lock:
            if _embedding_model is None:
                num_threads = max(2, (os.cpu_count() or 8) // 2)
                _embedding_model = TextEmbedding("BAAI/bge-small-en-v1.5", threads=num_threads)
                print(f"[RAG] FastEmbed model initialized with {num_threads} threads.", flush=True)

    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        batch_embeddings = list(_embedding_model.embed(batch, batch_size=batch_size))
        all_embeddings.extend([e.tolist() for e in batch_embeddings])
    return all_embeddings


def ensure_collection():
    client = get_qdrant()
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in existing:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
    # Ensure keyword index on "category" payload field for filtered queries
    try:
        from qdrant_client.models import PayloadSchemaType
        client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name="category",
            field_schema=PayloadSchemaType.KEYWORD,
        )
    except Exception:
        pass


def get_collection_count() -> int:
    try:
        ensure_collection()
        return get_qdrant().count(collection_name=COLLECTION_NAME).count
    except Exception:
        return 0


def chunk_text(text: str, chunk_size: int = 250, overlap: int = 40) -> list:
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        chunk = " ".join(words[start:start + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
        start += chunk_size - overlap
    return chunks


def ingest_documents(stream_batch_size: int = 128):
    ensure_collection()

    existing_count = get_collection_count()
    if existing_count > 0:
        print(f"[RAG] {existing_count} chunks already stored in Qdrant. Skipping ingestion.")
        return

    start_time = time.perf_counter()
    documents = load_all_documents(DRAFTS_DATA_PATH)
    if not documents:
        print("[RAG] No documents found.")
        return

    print("[RAG] Chunking and deduplicating documents...")
    all_items = []
    seen_hashes = set()
    duplicate_count = 0

    for doc in documents:
        for i, chunk in enumerate(chunk_text(doc["text"], chunk_size=250, overlap=40)):
            chunk_hash = hashlib.md5(chunk.encode("utf-8")).hexdigest()
            if chunk_hash in seen_hashes:
                duplicate_count += 1
                continue
            seen_hashes.add(chunk_hash)

            all_items.append({
                "id": str(uuid.uuid4()),
                "text": chunk,
                "metadata": {
                    "filename": doc["metadata"]["filename"],
                    "category": doc["metadata"]["category"],
                    "chunk_index": i,
                }
            })

    total_chunks = len(all_items)
    print(f"[RAG] Prepared {total_chunks} unique chunks ({duplicate_count} duplicates skipped).")
    print(f"[RAG] Beginning Streaming Ingestion (Batch size = {stream_batch_size})...")

    client = get_qdrant()
    total_stored = 0

    for i in range(0, total_chunks, stream_batch_size):
        batch_items = all_items[i:i + stream_batch_size]
        batch_texts = [item["text"] for item in batch_items]
        
        batch_num = i // stream_batch_size + 1
        total_batches = (total_chunks + stream_batch_size - 1) // stream_batch_size
        print(f"[RAG] Embedding batch {batch_num}/{total_batches} ({len(batch_texts)} chunks)...", flush=True)

        batch_embeddings = get_embeddings(batch_texts, batch_size=32)

        points = [
            PointStruct(
                id=batch_items[j]["id"],
                vector=batch_embeddings[j],
                payload={
                    "text": batch_items[j]["text"],
                    **batch_items[j]["metadata"]
                }
            )
            for j in range(len(batch_items))
        ]

        for attempt in range(3):
            try:
                client.upsert(collection_name=COLLECTION_NAME, points=points)
                total_stored += len(points)
                elapsed = time.perf_counter() - start_time
                rate = total_stored / elapsed if elapsed > 0 else 0
                pct = (total_stored / total_chunks) * 100
                print(
                    f"[RAG] Streamed {total_stored}/{total_chunks} chunks ({pct:.1f}%) "
                    f"to Qdrant | Rate: {rate:.1f} chunks/sec | Elapsed: {elapsed:.1f}s",
                    flush=True
                )
                break
            except Exception as e:
                if attempt == 2:
                    print(f"\n[RAG] Failed stream batch at index {i} after 3 attempts: {e}")
                else:
                    print(f"\n[RAG] Retry {attempt + 1} for batch index {i}...")
                    time.sleep(2)

    total_time = time.perf_counter() - start_time
    print(f"\n[RAG] Ingestion completed in {total_time:.2f}s! Total chunks in Qdrant: {get_collection_count()}")


def search_drafts(query: str, n_results: int = 5, category_filter: str = None) -> list:
    try:
        ensure_collection()

        if get_collection_count() == 0:
            return []

        query_embedding = get_embeddings([query])[0]

        query_filter = None
        if category_filter:
            query_filter = Filter(
                must=[FieldCondition(key="category", match=MatchValue(value=category_filter))]
            )

        try:
            results = get_qdrant().search(
                collection_name=COLLECTION_NAME,
                query_vector=query_embedding,
                limit=n_results,
                query_filter=query_filter,
                with_payload=True,
            )
        except Exception as filter_err:
            # Fallback to search without filter if category payload index is not ready
            print(f"[RAG] Filter search failed ({filter_err}), falling back to un-filtered search...")
            results = get_qdrant().search(
                collection_name=COLLECTION_NAME,
                query_vector=query_embedding,
                limit=n_results,
                with_payload=True,
            )

        output = []
        for r in results:
            if r.score < 0.35:
                continue
            output.append({
                "text": r.payload.get("text", ""),
                "metadata": {
                    "filename": r.payload.get("filename", ""),
                    "category": r.payload.get("category", ""),
                    "chunk_index": r.payload.get("chunk_index", 0),
                },
                "score": r.score,
            })

        return output
    except Exception as e:
        print(f"[RAG] search_drafts failed: {e}")
        return []