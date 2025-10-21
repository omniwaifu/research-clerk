"""Apply saved reorganization suggestions."""
import json
import re
from pathlib import Path
from .backends.local_sqlite import LocalSQLiteBackend
from .config import find_zotero_database


def validate_reorganization(data: dict) -> list[str]:
    """
    Validate reorganization JSON schema.

    Returns list of error messages (empty if valid).
    """
    errors = []

    # Check top-level structure
    if not isinstance(data, dict):
        errors.append("Root must be a JSON object")
        return errors

    if "moves" not in data:
        errors.append("Missing required 'moves' field")
        return errors

    if not isinstance(data["moves"], list):
        errors.append("'moves' must be a list")
        return errors

    if len(data["moves"]) == 0:
        # Empty list is OK - means no reorganization needed
        return []

    # Validate each move
    for i, move in enumerate(data["moves"]):
        prefix = f"Move {i}"

        if not isinstance(move, dict):
            errors.append(f"{prefix}: must be an object")
            continue

        # Required fields
        if "item_key" not in move:
            errors.append(f"{prefix}: missing 'item_key'")
        elif not isinstance(move["item_key"], str):
            errors.append(f"{prefix}: 'item_key' must be a string")
        elif not re.match(r'^[A-Z0-9]{8}$', move["item_key"]):
            errors.append(f"{prefix}: 'item_key' must be 8 uppercase alphanumeric characters (got: {move['item_key']})")

        if "current_path" not in move:
            errors.append(f"{prefix}: missing 'current_path'")
        elif not isinstance(move["current_path"], str):
            errors.append(f"{prefix}: 'current_path' must be a string")
        elif not move["current_path"].strip():
            errors.append(f"{prefix}: 'current_path' cannot be empty")

        if "new_path" not in move:
            errors.append(f"{prefix}: missing 'new_path'")
        elif not isinstance(move["new_path"], str):
            errors.append(f"{prefix}: 'new_path' must be a string")
        elif not move["new_path"].strip():
            errors.append(f"{prefix}: 'new_path' cannot be empty")
        elif move["new_path"].count('/') > 2:
            errors.append(f"{prefix}: 'new_path' exceeds max 3 levels (got: {move['new_path']})")

        # Optional fields
        if "title" in move and not isinstance(move["title"], str):
            errors.append(f"{prefix}: 'title' must be a string")

        if "reasoning" in move and not isinstance(move["reasoning"], str):
            errors.append(f"{prefix}: 'reasoning' must be a string")

    return errors


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
        # Build collection key maps (existing and new)
        existing_collections = backend.list_collections()
        new_collection_keys = {}

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

            # Create new collection hierarchy if needed
            parts = new_path.split('/')
            parent_key = None

            for i, part in enumerate(parts):
                path_so_far = '/'.join(parts[:i+1])

                # Check if exists in original collections
                existing_key = None
                for key, coll in existing_collections.items():
                    if coll["path"] == path_so_far:
                        existing_key = key
                        break

                if existing_key:
                    parent_key = existing_key
                elif path_so_far in new_collection_keys:
                    parent_key = new_collection_keys[path_so_far]
                else:
                    # Create this collection
                    new_key = backend.create_collection(part, parent_key)
                    new_collection_keys[path_so_far] = new_key
                    parent_key = new_key

            # Get final collection key
            final_key = None
            for key, coll in existing_collections.items():
                if coll["path"] == new_path:
                    final_key = key
                    break
            if not final_key:
                final_key = new_collection_keys.get(new_path)

            if not final_key:
                print(f"  ✗ Error: Could not find or create collection '{new_path}'")
                continue

            # Move item: add to new collection
            backend.add_to_collection(item_key, final_key)

            # Remove from old collection
            backend.remove_from_collection(item_key, current_collection_key)

    print(f"\n✓ Applied {len(moves)} reorganizations")
