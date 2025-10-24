"""Shared utilities for research-clerk."""
import json
import re
from typing import Dict, Any, List, Optional


# Constants
MAX_COLLECTION_DEPTH = 3
MAX_TAGS_PER_ITEM = 5
ITEM_KEY_PATTERN = r'^[A-Z0-9]{8}$'
JSON_CODE_BLOCK_PATTERN = r'```json\s*(\{.*?\})\s*```'


def extract_json_from_markdown(text: str) -> Optional[dict]:
    """
    Extract JSON from markdown code block.

    Args:
        text: Text potentially containing a ```json ... ``` block

    Returns:
        Parsed JSON dict or None if not found or invalid
    """
    match = re.search(JSON_CODE_BLOCK_PATTERN, text, re.DOTALL)
    if not match:
        return None

    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def format_tool_response(message: str) -> dict:
    """
    Format message as MCP tool response.

    Args:
        message: Message to return from tool

    Returns:
        Properly formatted tool response dict
    """
    return {"content": [{"type": "text", "text": message}]}


def build_collection_hierarchy(
    collection_path: str,
    existing_collections: Dict[str, Dict[str, Any]],
    backend,
    new_collection_cache: Optional[Dict[str, str]] = None
) -> str:
    """
    Build collection hierarchy, creating collections as needed.

    Args:
        collection_path: Full path like "Computer Science/AI/NLP"
        existing_collections: Map of collection_key -> collection data with 'path' field
        backend: Database backend with create_collection method
        new_collection_cache: Optional dict to track newly created collections

    Returns:
        Collection key for the final (leaf) collection

    Raises:
        ValueError: If collection cannot be found or created
    """
    if new_collection_cache is None:
        new_collection_cache = {}

    # Build reverse lookup: path -> key
    collection_keys = {coll['path']: key for key, coll in existing_collections.items()}
    collection_keys.update(new_collection_cache)

    # Build hierarchy level by level
    parts = collection_path.split('/')
    parent_key = None

    for i, part in enumerate(parts):
        path_so_far = '/'.join(parts[:i+1])

        if path_so_far not in collection_keys:
            # Create this collection
            new_key = backend.create_collection(part, parent_key)
            collection_keys[path_so_far] = new_key
            new_collection_cache[path_so_far] = new_key
            parent_key = new_key
        else:
            parent_key = collection_keys[path_so_far]

    # Return final collection key
    return collection_keys[collection_path]


def validate_item_key(item_key: Any, item_label: str = "Item") -> Optional[str]:
    """
    Validate item key format.

    Args:
        item_key: Value to validate
        item_label: Label for error messages

    Returns:
        Error message if invalid, None if valid
    """
    if not isinstance(item_key, str):
        return f"{item_label}: 'item_key' must be a string"
    if not re.match(ITEM_KEY_PATTERN, item_key):
        return f"{item_label}: 'item_key' must be 8 uppercase alphanumeric characters (got: {item_key})"
    return None


def validate_collection_path(path: Any, field_name: str, item_label: str = "Item") -> Optional[str]:
    """
    Validate collection path format and depth.

    Args:
        path: Path value to validate
        field_name: Name of the field being validated
        item_label: Label for error messages

    Returns:
        Error message if invalid, None if valid
    """
    if not isinstance(path, str):
        return f"{item_label}: '{field_name}' must be a string"
    if not path.strip():
        return f"{item_label}: '{field_name}' cannot be empty"
    if path.count('/') > MAX_COLLECTION_DEPTH - 1:
        return f"{item_label}: '{field_name}' exceeds max {MAX_COLLECTION_DEPTH} levels (got: {path})"
    return None


def validate_tags(tags: Any, item_label: str = "Item") -> Optional[str]:
    """
    Validate tags list format and length.

    Args:
        tags: Tags value to validate
        item_label: Label for error messages

    Returns:
        Error message if invalid, None if valid
    """
    if not isinstance(tags, list):
        return f"{item_label}: 'tags' must be a list"
    if not all(isinstance(t, str) for t in tags):
        return f"{item_label}: all tags must be strings"
    if len(tags) > MAX_TAGS_PER_ITEM:
        return f"{item_label}: too many tags (max {MAX_TAGS_PER_ITEM}, got {len(tags)})"
    return None


def validate_suggestions(data: dict) -> List[str]:
    """
    Validate categorization suggestions JSON schema.

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

    # Empty list is OK
    if len(data["items"]) == 0:
        return []

    # Validate each item
    for i, item in enumerate(data["items"]):
        prefix = f"Item {i}"

        if not isinstance(item, dict):
            errors.append(f"{prefix}: must be an object")
            continue

        # Validate item_key
        if "item_key" not in item:
            errors.append(f"{prefix}: missing 'item_key'")
        else:
            error = validate_item_key(item["item_key"], prefix)
            if error:
                errors.append(error)

        # Validate collection_path
        if "collection_path" not in item:
            errors.append(f"{prefix}: missing 'collection_path'")
        else:
            error = validate_collection_path(item["collection_path"], "collection_path", prefix)
            if error:
                errors.append(error)

        # Validate optional fields
        if "tags" in item:
            error = validate_tags(item["tags"], prefix)
            if error:
                errors.append(error)

        if "title" in item and not isinstance(item["title"], str):
            errors.append(f"{prefix}: 'title' must be a string")

        if "reasoning" in item and not isinstance(item["reasoning"], str):
            errors.append(f"{prefix}: 'reasoning' must be a string")

    return errors


def validate_reorganization(data: dict) -> List[str]:
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

    # Empty list is OK
    if len(data["moves"]) == 0:
        return []

    # Validate each move
    for i, move in enumerate(data["moves"]):
        prefix = f"Move {i}"

        if not isinstance(move, dict):
            errors.append(f"{prefix}: must be an object")
            continue

        # Validate item_key
        if "item_key" not in move:
            errors.append(f"{prefix}: missing 'item_key'")
        else:
            error = validate_item_key(move["item_key"], prefix)
            if error:
                errors.append(error)

        # Validate current_path
        if "current_path" not in move:
            errors.append(f"{prefix}: missing 'current_path'")
        else:
            # current_path doesn't need depth check
            if not isinstance(move["current_path"], str):
                errors.append(f"{prefix}: 'current_path' must be a string")
            elif not move["current_path"].strip():
                errors.append(f"{prefix}: 'current_path' cannot be empty")

        # Validate new_path
        if "new_path" not in move:
            errors.append(f"{prefix}: missing 'new_path'")
        else:
            error = validate_collection_path(move["new_path"], "new_path", prefix)
            if error:
                errors.append(error)

        # Validate optional fields
        if "title" in move and not isinstance(move["title"], str):
            errors.append(f"{prefix}: 'title' must be a string")

        if "reasoning" in move and not isinstance(move["reasoning"], str):
            errors.append(f"{prefix}: 'reasoning' must be a string")

    return errors
