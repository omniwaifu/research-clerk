#!/usr/bin/env python3
"""Clean up duplicate collections in Zotero database."""
from research_clerk.backends.local_sqlite import LocalSQLiteBackend
from research_clerk.config import find_zotero_database
from collections import defaultdict


def cleanup_duplicate_collections():
    """Remove duplicate collections, keeping one instance of each path."""
    db_path = find_zotero_database()
    backend = LocalSQLiteBackend(db_path)

    with backend.connect(read_only=False) as backend:
        # Get all collections
        all_collections = backend.list_collections()

        # Group by path to find duplicates
        path_groups = defaultdict(list)
        for key, coll in all_collections.items():
            path_groups[coll['path']].append((key, coll))

        # Find duplicates
        duplicates_found = False
        for path, collections in path_groups.items():
            if len(collections) > 1:
                duplicates_found = True
                print(f"\nFound {len(collections)} duplicates of '{path}':")

                # Keep the first one, delete the rest
                keeper_key, keeper_coll = collections[0]
                keeper_id = keeper_coll['collectionID']
                print(f"  Keeping: {keeper_key} (ID: {keeper_id})")

                for dup_key, dup_coll in collections[1:]:
                    dup_id = dup_coll['collectionID']
                    print(f"  Deleting: {dup_key} (ID: {dup_id})")

                    # Move items from duplicate to keeper
                    cursor = backend.conn.execute(
                        "SELECT itemID FROM collectionItems WHERE collectionID = ?",
                        (dup_id,)
                    )
                    item_ids = [row[0] for row in cursor]

                    for item_id in item_ids:
                        # Check if item already in keeper collection
                        cursor = backend.conn.execute(
                            "SELECT 1 FROM collectionItems WHERE collectionID = ? AND itemID = ?",
                            (keeper_id, item_id)
                        )
                        if not cursor.fetchone():
                            # Get next orderIndex for keeper
                            cursor = backend.conn.execute(
                                "SELECT COALESCE(MAX(orderIndex), -1) + 1 FROM collectionItems WHERE collectionID = ?",
                                (keeper_id,)
                            )
                            order_index = cursor.fetchone()[0]

                            # Add to keeper
                            backend.conn.execute(
                                "INSERT INTO collectionItems (collectionID, itemID, orderIndex) VALUES (?, ?, ?)",
                                (keeper_id, item_id, order_index)
                            )
                            print(f"    Moved item {item_id} to keeper collection")

                    # Delete all items from duplicate collection
                    backend.conn.execute(
                        "DELETE FROM collectionItems WHERE collectionID = ?",
                        (dup_id,)
                    )

                    # Delete the duplicate collection
                    backend.conn.execute(
                        "DELETE FROM collections WHERE collectionID = ?",
                        (dup_id,)
                    )

        if not duplicates_found:
            print("No duplicate collections found")
        else:
            print("\n✓ Cleanup complete")


if __name__ == "__main__":
    cleanup_duplicate_collections()
