# research-clerk

AI-powered categorization for Zotero libraries using Claude Agent SDK.

## What it does

Analyzes unfiled papers and creates hierarchical collections with tags. Works directly with local Zotero database - no API keys or cloud sync required.

## Setup

```bash
uv sync
```

Zotero database auto-detected at `~/Zotero/zotero.sqlite`. Set `ZOTERO_DATA_DIR` for custom locations.

## Usage

### Categorize unfiled items

```bash
# Dry-run: analyze and save suggestions
python cli.py --batch-size 10

# Apply saved suggestions
python cli.py --apply-suggestions suggestions.json
```

### Reorganize existing structure

```bash
# Dry-run: analyze and suggest reorganization
python cli.py --reorganize

# Apply saved reorganization
python cli.py --apply-reorganization reorganization.json
```

### Batch processing

Use `--batch-size N` to process incrementally and avoid timeouts.

## Workflow

1. **Dry-run**: Agent analyzes items, saves JSON with categorizations and reasoning
2. **Review**: Inspect suggestions.json, edit if needed
3. **Apply**: Execute changes to database
4. **Repeat**: Run again for next batch (previously categorized items drop from unfiled list)

## Safety

- Auto-backup before writes
- Refuses to run if Zotero is open
- Atomic transactions with rollback on error
- Dry-run mode works while Zotero is running (read-only)
- Never deletes anything

## Architecture

Direct SQLite access with in-process MCP server. Agent uses tools to:
- List unfiled items and existing collections
- Get item metadata (abstracts, titles, tags)
- Create collections and add items

Rules enforced:
- Max 3 collection levels
- 2-5 tags per item
- Requires 3+ papers before creating subcategories
- Reuses existing collection structure

## Threat model

- Database corruption: mitigated by backup, lock check, transactions
- Duplicate collections: fixed - now checks existing before creating
- Attachments in collections: filtered out (they have parentItemID)
- Over-categorization: agent enforces depth/breadth rules
