"""
Sanity check for the vector store.

Run this after ingest.py. It asks the questions the demo depends on and prints
what comes back, so you find out now rather than in front of an audience
whether retrieval actually works.

The important test is the first one. None of the payments postmortems use the
phrase "connection pool" in their title or summary, so if that query returns
the payments cluster, semantic retrieval is doing real work. If it returns
nothing useful, the demo's headline moment does not exist.
"""

from pathlib import Path
import chromadb

ROOT = Path(__file__).resolve().parent.parent
CHROMA_DIR = ROOT / "data" / "chroma"

QUERIES = [
    "payments latency is spiking again, has this happened before",
    "what causes connection pool exhaustion",
    "service is slow but the database is healthy",
    "memory usage growing over time until pods restart",
    "we found out from customers instead of from monitoring",
    "what did we change to fix the recurring payments problem",
]


def main():
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = client.get_collection("postmortems")

    for q in QUERIES:
        print("=" * 78)
        print(f"QUERY: {q}")
        print("=" * 78)
        res = collection.query(query_texts=[q], n_results=4)
        for doc, meta, dist in zip(res["documents"][0],
                                   res["metadatas"][0],
                                   res["distances"][0]):
            first_line = doc.split("\n\n")[1].replace("\n", " ")[:110] \
                if "\n\n" in doc else doc[:110]
            print(f"  [{dist:.3f}] {meta['incident_id']:<9} "
                  f"{meta['service']:<14} {meta['section']:<11} {first_line}...")
        print()


if __name__ == "__main__":
    main()
