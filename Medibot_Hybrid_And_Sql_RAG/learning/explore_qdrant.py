"""
Explore Qdrant vector database contents
"""
from qdrant_client import QdrantClient
from pathlib import Path

# Path updated for learning folder location
QDRANT_PATH = Path(__file__).parent.parent / "backend" / "qdrant_data"

def explore():
    client = QdrantClient(path=str(QDRANT_PATH))

    # List all collections
    collections = client.get_collections().collections
    print("=" * 60)
    print("Collections in Qdrant:")
    print("=" * 60)
    for col in collections:
        print(f"  - {col.name}")

    # Get collection info
    collection_name = "medibot_docs_vectorstore"
    info = client.get_collection(collection_name)

    print(f"\n" + "=" * 60)
    print(f"Collection: {collection_name}")
    print("=" * 60)
    print(f"  Points count: {info.points_count}")
    print(f"  Vectors config: {info.config.params.vectors}")

    # Sample some points
    print(f"\n" + "=" * 60)
    print("Sample points (first 3):")
    print("=" * 60)

    points = client.scroll(
        collection_name=collection_name,
        limit=2,
        with_payload=True,
        with_vectors=True,  # Don't show vectors (too long)
    )[0]

    for i, point in enumerate(points):
        print(f"\n[Point {i+1}] ID: {point.id}")
        print(f"  Payload keys: {list(point.payload.keys())}")
        print(f"  Full payload: {point.payload}")
        # Show vector info (not full vectors - too long)
        if point.vector:
            if isinstance(point.vector, dict):
                # Named vectors (dense, sparse)
                print(f"  Vector names: {list(point.vector.keys())}")
                for name, vec in point.vector.items():
                    if hasattr(vec, 'indices'):  # Sparse vector
                        print(f"    {name}: sparse, {len(vec.indices)} non-zero values")
                    else:  # Dense vector
                        print(f"    {name}: dense, {len(vec)} dimensions, first 5: {vec[:5]}")
            else:
                # Single vector
                print(f"  Vector: {len(point.vector)} dimensions, first 5: {point.vector[:5]}")

    # Count by collection (commented out - need to debug metadata first)
    # print(f"\n" + "=" * 60)
    # print("Chunks per document collection:")
    # print("=" * 60)

    client.close()

if __name__ == "__main__":
    explore()
