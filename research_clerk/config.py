"""Configuration management for research-clerk."""
import os
from pathlib import Path
from .backends.local_sqlite import LocalSQLiteBackend


def find_zotero_database() -> Path:
    """Auto-detect zotero database location."""
    # common locations
    candidates = [
        Path.home() / "Zotero" / "zotero.sqlite",
        Path.home() / ".zotero" / "zotero" / "zotero.sqlite",
        Path.home() / "snap" / "zotero-snap" / "common" / "Zotero" / "zotero.sqlite",
    ]

    # check ZOTERO_DATA_DIR env var
    data_dir = os.getenv("ZOTERO_DATA_DIR")
    if data_dir:
        candidates.insert(0, Path(data_dir) / "zotero.sqlite")

    for path in candidates:
        if path.exists():
            return path

    raise ValueError(
        "Zotero database not found. Checked:\n" +
        "\n".join(f"  - {p}" for p in candidates) +
        "\n\nSet ZOTERO_DATA_DIR environment variable if using custom location."
    )


def get_zotero_backend(read_only: bool = False) -> LocalSQLiteBackend:
    """
    Get zotero backend (local sqlite).

    Args:
        read_only: If True, open in read-only mode (safe while zotero running)

    Returns:
        LocalSQLiteBackend: Backend connected to local zotero database
    """
    db_path = find_zotero_database()
    backend = LocalSQLiteBackend(db_path)
    backend.connect(read_only=read_only)
    return backend
