"""Local SQLite backend for Zotero database access."""
import sqlite3
import shutil
import secrets
import string
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any


def generate_key() -> str:
    """Generate 8-character alphanumeric key like zotero does."""
    chars = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(8))


class LocalSQLiteBackend:
    """Direct sqlite access to zotero database with safety checks."""
    
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.backup_path: Optional[Path] = None
        self.conn: Optional[sqlite3.Connection] = None
        
        if not self.db_path.exists():
            raise ValueError(f"Zotero database not found: {db_path}")
    
    def check_zotero_running(self) -> bool:
        """Check if zotero is running by attempting exclusive lock."""
        try:
            test_conn = sqlite3.connect(self.db_path, timeout=0.1)
            test_conn.execute("BEGIN EXCLUSIVE")
            test_conn.rollback()
            test_conn.close()
            return False
        except sqlite3.OperationalError:
            return True
    
    def create_backup(self) -> Path:
        """Create timestamped backup of database."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = self.db_path.parent / "backups"
        backup_dir.mkdir(exist_ok=True)
        
        self.backup_path = backup_dir / f"zotero_backup_{timestamp}.sqlite"
        shutil.copy2(self.db_path, self.backup_path)
        print(f"✓ Backup created: {self.backup_path}")
        return self.backup_path
    
    def connect(self, read_only: bool = False):
        """Connect to database."""
        if read_only:
            # open in read-only mode
            uri = f"file:{self.db_path}?mode=ro"
            self.conn = sqlite3.connect(uri, uri=True)
        else:
            # check zotero not running
            if self.check_zotero_running():
                raise RuntimeError(
                    "Zotero is running! Close it before making changes.\\n"
                    "This prevents database corruption."
                )
            
            # create backup
            self.create_backup()
            
            # connect with write access
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row
        
        return self
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            if exc_type:
                print(f"✗ Error occurred, rolling back: {exc_val}")
                self.conn.rollback()
            else:
                self.conn.commit()
            self.conn.close()
    
    def get_library_id(self) -> int:
        """Get the libraryID (usually 1 for local)."""
        cursor = self.conn.execute("SELECT libraryID FROM libraries LIMIT 1")
        row = cursor.fetchone()
        return row[0] if row else 1
    
    def list_unfiled_items(self) -> List[Dict[str, Any]]:
        """Get items not in any collection (excluding attachments)."""
        query = """
        SELECT DISTINCT
            i.itemID,
            i.key,
            iv.value AS title,
            it.typeName AS itemType
        FROM items i
        LEFT JOIN collectionItems ci ON i.itemID = ci.itemID
        LEFT JOIN itemAttachments ia ON i.itemID = ia.itemID
        LEFT JOIN itemNotes inotes ON i.itemID = inotes.itemID
        LEFT JOIN itemData id ON i.itemID = id.itemID
        LEFT JOIN itemDataValues iv ON id.valueID = iv.valueID
        LEFT JOIN fields f ON id.fieldID = f.fieldID
        LEFT JOIN itemTypes it ON i.itemTypeID = it.itemTypeID
        WHERE ci.itemID IS NULL
          AND ia.itemID IS NULL
          AND inotes.itemID IS NULL
          AND i.itemID NOT IN (SELECT itemID FROM deletedItems)
          AND f.fieldName = 'title'
        ORDER BY i.dateAdded DESC
        """
        
        cursor = self.conn.execute(query)
        items = []
        for row in cursor:
            items.append({
                "itemID": row[0],
                "key": row[1],
                "title": row[2] or "Untitled",
                "itemType": row[3] or "unknown"
            })
        return items
    
    def get_item_details(self, item_key: str) -> Dict[str, Any]:
        """Get full metadata for an item."""
        # get basic item info
        cursor = self.conn.execute(
            "SELECT itemID, itemTypeID FROM items WHERE key = ?",
            (item_key,)
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Item not found: {item_key}")
        
        item_id, item_type_id = row
        
        # get all field data
        field_query = """
        SELECT f.fieldName, idv.value
        FROM itemData id
        JOIN fields f ON id.fieldID = f.fieldID
        JOIN itemDataValues idv ON id.valueID = idv.valueID
        WHERE id.itemID = ?
        """
        cursor = self.conn.execute(field_query, (item_id,))
        
        fields = {"itemID": item_id, "key": item_key}
        for field_row in cursor:
            fields[field_row[0]] = field_row[1]
        
        # get tags
        tag_query = """
        SELECT t.name
        FROM itemTags it
        JOIN tags t ON it.tagID = t.tagID
        WHERE it.itemID = ?
        """
        cursor = self.conn.execute(tag_query, (item_id,))
        fields["tags"] = [row[0] for row in cursor]
        
        return fields
    
    def list_collections(self) -> Dict[str, Dict[str, Any]]:
        """Get all collections with hierarchy."""
        query = """
        SELECT collectionID, collectionName, parentCollectionID, key
        FROM collections
        WHERE collectionID NOT IN (SELECT collectionID FROM deletedCollections)
        ORDER BY collectionName
        """
        cursor = self.conn.execute(query)
        
        collections = {}
        for row in cursor:
            coll_id, name, parent_id, key = row
            collections[key] = {
                "collectionID": coll_id,
                "name": name,
                "parentCollectionID": parent_id,
                "key": key
            }
        
        # build hierarchy paths
        def get_path(key):
            coll = collections.get(key)
            if not coll:
                return ""
            parent_id = coll["parentCollectionID"]
            if parent_id:
                # find parent key
                parent_key = next(
                    (k for k, v in collections.items() if v["collectionID"] == parent_id),
                    None
                )
                if parent_key:
                    parent_path = get_path(parent_key)
                    return f"{parent_path}/{coll['name']}" if parent_path else coll['name']
            return coll['name']
        
        for key in collections:
            collections[key]["path"] = get_path(key)
        
        return collections
    
    def create_collection(self, name: str, parent_key: Optional[str] = None) -> str:
        """Create a new collection."""
        library_id = self.get_library_id()
        key = generate_key()
        
        # get parent ID if specified
        parent_id = None
        if parent_key:
            cursor = self.conn.execute(
                "SELECT collectionID FROM collections WHERE key = ?",
                (parent_key,)
            )
            row = cursor.fetchone()
            if row:
                parent_id = row[0]
            else:
                raise ValueError(f"Parent collection not found: {parent_key}")
        
        # insert collection
        self.conn.execute("""
            INSERT INTO collections (
                collectionName, parentCollectionID, libraryID, key, 
                version, synced, clientDateModified
            ) VALUES (?, ?, ?, ?, 0, 0, CURRENT_TIMESTAMP)
        """, (name, parent_id, library_id, key))
        
        print(f"  ✓ Created collection: {name} ({key})")
        return key
    
    def add_to_collection(self, item_key: str, collection_key: str):
        """Add an item to a collection."""
        # get itemID
        cursor = self.conn.execute("SELECT itemID FROM items WHERE key = ?", (item_key,))
        item_row = cursor.fetchone()
        if not item_row:
            raise ValueError(f"Item not found: {item_key}")
        item_id = item_row[0]
        
        # get collectionID
        cursor = self.conn.execute("SELECT collectionID FROM collections WHERE key = ?", (collection_key,))
        coll_row = cursor.fetchone()
        if not coll_row:
            raise ValueError(f"Collection not found: {collection_key}")
        collection_id = coll_row[0]
        
        # check if already in collection
        cursor = self.conn.execute(
            "SELECT 1 FROM collectionItems WHERE itemID = ? AND collectionID = ?",
            (item_id, collection_id)
        )
        if cursor.fetchone():
            print("  - Item already in collection (skipping)")
            return
        
        # get next orderIndex
        cursor = self.conn.execute(
            "SELECT COALESCE(MAX(orderIndex), -1) + 1 FROM collectionItems WHERE collectionID = ?",
            (collection_id,)
        )
        order_index = cursor.fetchone()[0]
        
        # insert
        self.conn.execute("""
            INSERT INTO collectionItems (collectionID, itemID, orderIndex)
            VALUES (?, ?, ?)
        """, (collection_id, item_id, order_index))
        
        print("  ✓ Added item to collection")
    
    def add_tags(self, item_key: str, tag_names: List[str]):
        """Add tags to an item."""
        # get itemID
        cursor = self.conn.execute("SELECT itemID FROM items WHERE key = ?", (item_key,))
        item_row = cursor.fetchone()
        if not item_row:
            raise ValueError(f"Item not found: {item_key}")
        item_id = item_row[0]
        
        for tag_name in tag_names:
            # get or create tag
            cursor = self.conn.execute("SELECT tagID FROM tags WHERE name = ?", (tag_name,))
            tag_row = cursor.fetchone()
            
            if tag_row:
                tag_id = tag_row[0]
            else:
                cursor = self.conn.execute("INSERT INTO tags (name) VALUES (?)", (tag_name,))
                tag_id = cursor.lastrowid
            
            # check if already tagged
            cursor = self.conn.execute(
                "SELECT 1 FROM itemTags WHERE itemID = ? AND tagID = ?",
                (item_id, tag_id)
            )
            if cursor.fetchone():
                continue
            
            # add tag (type 0 = manual tag)
            self.conn.execute(
                "INSERT INTO itemTags (itemID, tagID, type) VALUES (?, ?, 0)",
                (item_id, tag_id)
            )

        print(f"  ✓ Added tags: {', '.join(tag_names)}")

    def list_filed_items(self) -> List[Dict[str, Any]]:
        """Get items that ARE in collections (excluding attachments)."""
        query = """
        SELECT DISTINCT
            i.itemID,
            i.key,
            iv.value AS title,
            it.typeName AS itemType
        FROM items i
        JOIN collectionItems ci ON i.itemID = ci.itemID
        LEFT JOIN itemAttachments ia ON i.itemID = ia.itemID
        LEFT JOIN itemNotes inotes ON i.itemID = inotes.itemID
        LEFT JOIN itemData id ON i.itemID = id.itemID
        LEFT JOIN itemDataValues iv ON id.valueID = iv.valueID
        LEFT JOIN fields f ON id.fieldID = f.fieldID
        LEFT JOIN itemTypes it ON i.itemTypeID = it.itemTypeID
        WHERE ia.itemID IS NULL
          AND inotes.itemID IS NULL
          AND i.itemID NOT IN (SELECT itemID FROM deletedItems)
          AND f.fieldName = 'title'
        GROUP BY i.itemID, i.key, iv.value, it.typeName
        ORDER BY i.dateAdded DESC
        """

        cursor = self.conn.execute(query)
        items = []
        for row in cursor:
            items.append({
                "itemID": row[0],
                "key": row[1],
                "title": row[2] or "Untitled",
                "itemType": row[3] or "unknown"
            })
        return items

    def get_item_collections(self, item_key: str) -> List[str]:
        """Get full collection paths for an item."""
        query = """
        SELECT c.key
        FROM collectionItems ci
        JOIN collections c ON ci.collectionID = c.collectionID
        JOIN items i ON ci.itemID = i.itemID
        WHERE i.key = ?
          AND c.collectionID NOT IN (SELECT collectionID FROM deletedCollections)
        """
        cursor = self.conn.execute(query, (item_key,))

        collections_dict = self.list_collections()
        paths = []
        for row in cursor:
            coll_key = row[0]
            if coll_key in collections_dict:
                paths.append(collections_dict[coll_key]["path"])

        return paths

    def remove_from_collection(self, item_key: str, collection_key: str):
        """Remove an item from a collection."""
        # get itemID
        cursor = self.conn.execute("SELECT itemID FROM items WHERE key = ?", (item_key,))
        item_row = cursor.fetchone()
        if not item_row:
            raise ValueError(f"Item not found: {item_key}")
        item_id = item_row[0]

        # get collectionID
        cursor = self.conn.execute("SELECT collectionID FROM collections WHERE key = ?", (collection_key,))
        coll_row = cursor.fetchone()
        if not coll_row:
            raise ValueError(f"Collection not found: {collection_key}")
        collection_id = coll_row[0]

        # delete
        self.conn.execute(
            "DELETE FROM collectionItems WHERE itemID = ? AND collectionID = ?",
            (item_id, collection_id)
        )

        print("  ✓ Removed item from collection")
