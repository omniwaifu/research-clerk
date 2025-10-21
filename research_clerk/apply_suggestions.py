"""Apply saved categorization suggestions."""
import json
import re
from pathlib import Path
from .backends.local_sqlite import LocalSQLiteBackend
from .config import find_zotero_database


def validate_suggestions(data: dict) -> list[str]:
    """
    Validate suggestions JSON schema.

    Returns list of error messages (empty if valid).
    """
    errors = []

    # Check top-level structure
    if not isinstance(data, dict):
        errors.append("Root must be a JSON object")
        return errors

    if "items" not in data:
        errors.append("Missing required 'items' field")
        return errors

    if not isinstance(data["items"], list):
        errors.append("'items' must be a list")
        return errors

    # Empty list is OK - means no items to categorize
    if len(data["items"]) == 0:
        return []

    # Validate each item
    for i, item in enumerate(data["items"]):
        prefix = f"Item {i}"

        if not isinstance(item, dict):
            errors.append(f"{prefix}: must be an object")
            continue

        # Required fields
        if "item_key" not in item:
            errors.append(f"{prefix}: missing 'item_key'")
        elif not isinstance(item["item_key"], str):
            errors.append(f"{prefix}: 'item_key' must be a string")
        elif not re.match(r'^[A-Z0-9]{8}$', item["item_key"]):
            errors.append(f"{prefix}: 'item_key' must be 8 uppercase alphanumeric characters (got: {item['item_key']})")

        if "collection_path" not in item:
            errors.append(f"{prefix}: missing 'collection_path'")
        elif not isinstance(item["collection_path"], str):
            errors.append(f"{prefix}: 'collection_path' must be a string")
        elif not item["collection_path"].strip():
            errors.append(f"{prefix}: 'collection_path' cannot be empty")
        elif item["collection_path"].count('/') > 2:
            errors.append(f"{prefix}: 'collection_path' exceeds max 3 levels (got: {item['collection_path']})")

        # Optional fields
        if "tags" in item:
            if not isinstance(item["tags"], list):
                errors.append(f"{prefix}: 'tags' must be a list")
            elif not all(isinstance(t, str) for t in item["tags"]):
                errors.append(f"{prefix}: all tags must be strings")
            elif len(item["tags"]) > 5:
                errors.append(f"{prefix}: too many tags (max 5, got {len(item['tags'])})")

        if "title" in item and not isinstance(item["title"], str):
            errors.append(f"{prefix}: 'title' must be a string")

        if "reasoning" in item and not isinstance(item["reasoning"], str):
            errors.append(f"{prefix}: 'reasoning' must be a string")

    return errors


def apply_suggestions(suggestions_file: Path):
    """
    Apply categorization suggestions from a saved file.

    Args:
        suggestions_file: Path to JSON file with suggestions
    """
    with open(suggestions_file) as f:
        suggestions = json.load(f)

    # Validate schema
    errors = validate_suggestions(suggestions)
    if errors:
        print(f"✗ Invalid suggestions file: {suggestions_file}")
        for error in errors:
            print(f"  - {error}")
        raise ValueError(f"Suggestions file failed validation with {len(errors)} error(s)")

    print(f"📂 Loading suggestions from: {suggestions_file}")
    print(f"   {len(suggestions['items'])} items to categorize\n")

    # Connect to database
    db_path = find_zotero_database()
    backend = LocalSQLiteBackend(db_path)

    with backend.connect(read_only=False) as backend:
        # Build collection key map from existing collections
        existing_collections = backend.list_collections()
        collection_keys = {coll['path']: key for key, coll in existing_collections.items()}

        # Process each item
        for item in suggestions['items']:
            item_key = item['item_key']
            collection_path = item['collection_path']
            tags = item.get('tags', [])

            print(f"\n{'='*60}")
            print(f"Item: {item.get('title', item_key)}")
            print(f"Collection: {collection_path}")
            print(f"Tags: {', '.join(tags)}")
            print(f"Reasoning: {item.get('reasoning', 'N/A')}")
            print(f"{'='*60}")

            # Create collection hierarchy if needed
            parts = collection_path.split('/')
            parent_key = None

            for i, part in enumerate(parts):
                path_so_far = '/'.join(parts[:i+1])

                if path_so_far not in collection_keys:
                    # Create this collection
                    new_key = backend.create_collection(part, parent_key)
                    collection_keys[path_so_far] = new_key
                    parent_key = new_key
                else:
                    parent_key = collection_keys[path_so_far]

            # Add item to final collection
            final_key = collection_keys[collection_path]
            backend.add_to_collection(item_key, final_key)

            # Add tags
            if tags:
                backend.add_tags(item_key, tags)

    print(f"\n✓ Applied {len(suggestions['items'])} categorizations")
