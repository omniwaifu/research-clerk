"""Apply saved categorization suggestions."""
import json
from pathlib import Path
from .backends.local_sqlite import LocalSQLiteBackend
from .config import find_zotero_database
from .utils import validate_suggestions, build_collection_hierarchy


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
        new_collection_cache = {}

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

            # Create collection hierarchy if needed and get final collection key
            final_key = build_collection_hierarchy(
                collection_path,
                existing_collections,
                backend,
                new_collection_cache
            )

            # Add item to final collection
            backend.add_to_collection(item_key, final_key)

            # Add tags
            if tags:
                backend.add_tags(item_key, tags)

    print(f"\n✓ Applied {len(suggestions['items'])} categorizations")
