"""Apply saved reorganization suggestions."""
import json
from pathlib import Path
from .backends.local_sqlite import LocalSQLiteBackend
from .config import find_zotero_database
from .utils import validate_reorganization, build_collection_hierarchy


def apply_reorganization(reorganization_file: Path):
    """
    Apply reorganization suggestions from a saved file.

    Args:
        reorganization_file: Path to JSON file with reorganization suggestions
    """
    with open(reorganization_file) as f:
        reorganization = json.load(f)

    # Validate schema
    errors = validate_reorganization(reorganization)
    if errors:
        print(f"✗ Invalid reorganization file: {reorganization_file}")
        for error in errors:
            print(f"  - {error}")
        raise ValueError(f"Reorganization file failed validation with {len(errors)} error(s)")

    moves = reorganization["moves"]

    if len(moves) == 0:
        print("No reorganization needed - structure is already optimal")
        return

    print(f"📂 Loading reorganization from: {reorganization_file}")
    print(f"   {len(moves)} items to reorganize\n")

    # Connect to database
    db_path = find_zotero_database()
    backend = LocalSQLiteBackend(db_path)

    with backend.connect(read_only=False) as backend:
        # Build collection key map from existing collections
        existing_collections = backend.list_collections()
        new_collection_cache = {}

        # Process each move
        for move in moves:
            item_key = move['item_key']
            current_path = move['current_path']
            new_path = move['new_path']

            print(f"\n{'='*60}")
            print(f"Item: {move.get('title', item_key)}")
            print(f"Current: {current_path}")
            print(f"New: {new_path}")
            print(f"Reasoning: {move.get('reasoning', 'N/A')}")
            print(f"{'='*60}")

            # Find current collection key
            current_collection_key = None
            for key, coll in existing_collections.items():
                if coll["path"] == current_path:
                    current_collection_key = key
                    break

            if not current_collection_key:
                print(f"  ⚠️  Warning: Current collection '{current_path}' not found, skipping move")
                continue

            # Create new collection hierarchy if needed and get final collection key
            try:
                final_key = build_collection_hierarchy(
                    new_path,
                    existing_collections,
                    backend,
                    new_collection_cache
                )
            except ValueError as e:
                print(f"  ✗ Error: {e}")
                continue

            # Move item: add to new collection
            backend.add_to_collection(item_key, final_key)

            # Remove from old collection
            backend.remove_from_collection(item_key, current_collection_key)

    print(f"\n✓ Applied {len(moves)} reorganizations")
