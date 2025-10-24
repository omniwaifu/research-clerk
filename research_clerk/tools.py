"""Zotero tools for the categorization agent."""
import json
from claude_agent_sdk import tool
from .config import get_zotero_backend
from .utils import format_tool_response


# NOTE: tools run in read-only mode for reads, write mode for writes
# the backend handles safety (backups, checking zotero not running, etc)


@tool(
    name="list_unfiled_items",
    description="Get all papers not in any collection",
    input_schema={"type": "object", "properties": {}, "additionalProperties": False}
)
async def list_unfiled_items(args):
    """List all items not currently in any collection."""
    with get_zotero_backend(read_only=True) as backend:
        unfiled = backend.list_unfiled_items()

    return format_tool_response(json.dumps(unfiled, indent=2))


@tool(
    name="get_item_details",
    description="Get full metadata for a specific item including abstract and keywords",
    input_schema={
        "type": "object",
        "properties": {
            "item_key": {
                "type": "string",
                "description": "The Zotero item key"
            }
        },
        "required": ["item_key"],
        "additionalProperties": False
    }
)
async def get_item_details(args):
    """Fetch detailed metadata for a specific item."""
    with get_zotero_backend(read_only=True) as backend:
        metadata = backend.get_item_details(args["item_key"])

    return format_tool_response(json.dumps(metadata, indent=2))


@tool(
    name="list_collections",
    description="Get all existing collections with their hierarchical structure",
    input_schema={"type": "object", "properties": {}, "additionalProperties": False}
)
async def list_collections(args):
    """List all collections with their hierarchy."""
    with get_zotero_backend(read_only=True) as backend:
        collections = backend.list_collections()

    return format_tool_response(json.dumps(collections, indent=2))


@tool(
    name="create_collection",
    description="Create a new collection, optionally nested under a parent collection",
    input_schema={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Name of the new collection"
            },
            "parent_key": {
                "type": "string",
                "description": "Optional: parent collection key for nesting"
            }
        },
        "required": ["name"],
        "additionalProperties": False
    }
)
async def create_collection(args):
    """Create a new collection in Zotero."""
    with get_zotero_backend(read_only=False) as backend:
        new_key = backend.create_collection(args["name"], args.get("parent_key"))

    msg = f"Created collection '{args['name']}' with key {new_key}"
    if args.get("parent_key"):
        msg += f" under parent {args['parent_key']}"
    return format_tool_response(msg)


@tool(
    name="add_to_collection",
    description="Add an item to a collection",
    input_schema={
        "type": "object",
        "properties": {
            "item_key": {
                "type": "string",
                "description": "The item key to add"
            },
            "collection_key": {
                "type": "string",
                "description": "The collection key to add the item to"
            }
        },
        "required": ["item_key", "collection_key"],
        "additionalProperties": False
    }
)
async def add_to_collection(args):
    """Add an item to a collection."""
    with get_zotero_backend(read_only=False) as backend:
        backend.add_to_collection(args["item_key"], args["collection_key"])

    return format_tool_response(f"Added item {args['item_key']} to collection {args['collection_key']}")


@tool(
    name="add_tags_to_item",
    description="Add tags to an item",
    input_schema={
        "type": "object",
        "properties": {
            "item_key": {
                "type": "string",
                "description": "The item key to tag"
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of tags to add"
            }
        },
        "required": ["item_key", "tags"],
        "additionalProperties": False
    }
)
async def add_tags_to_item(args):
    """Add tags to an item."""
    with get_zotero_backend(read_only=False) as backend:
        backend.add_tags(args["item_key"], args["tags"])

    return format_tool_response(f"Added tags {args['tags']} to item {args['item_key']}")


@tool(
    name="list_filed_items",
    description="Get all papers that are already in collections (for reorganization)",
    input_schema={"type": "object", "properties": {}, "additionalProperties": False}
)
async def list_filed_items(args):
    """List all items that are already in collections."""
    with get_zotero_backend(read_only=True) as backend:
        filed = backend.list_filed_items()

    return format_tool_response(json.dumps(filed, indent=2))


@tool(
    name="get_item_collections",
    description="Get the collection paths an item is currently in",
    input_schema={
        "type": "object",
        "properties": {
            "item_key": {
                "type": "string",
                "description": "The Zotero item key"
            }
        },
        "required": ["item_key"],
        "additionalProperties": False
    }
)
async def get_item_collections(args):
    """Get collection paths for an item."""
    with get_zotero_backend(read_only=True) as backend:
        paths = backend.get_item_collections(args["item_key"])

    return format_tool_response(json.dumps(paths, indent=2))


@tool(
    name="remove_from_collection",
    description="Remove an item from a collection (for reorganization)",
    input_schema={
        "type": "object",
        "properties": {
            "item_key": {
                "type": "string",
                "description": "The item key to remove"
            },
            "collection_key": {
                "type": "string",
                "description": "The collection key to remove the item from"
            }
        },
        "required": ["item_key", "collection_key"],
        "additionalProperties": False
    }
)
async def remove_from_collection(args):
    """Remove an item from a collection."""
    with get_zotero_backend(read_only=False) as backend:
        backend.remove_from_collection(args["item_key"], args["collection_key"])

    return format_tool_response(f"Removed item {args['item_key']} from collection {args['collection_key']}")


# Export all tools for the MCP server
ALL_TOOLS = [
    list_unfiled_items,
    get_item_details,
    list_collections,
    create_collection,
    add_to_collection,
    add_tags_to_item,
]

# Reorganization tools (separate list)
REORGANIZE_TOOLS = [
    list_filed_items,
    get_item_details,
    get_item_collections,
    list_collections,
    create_collection,
    add_to_collection,
    remove_from_collection,
]
