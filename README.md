# research-clerk

AI-powered categorization for Zotero libraries using Claude Agent SDK.

## What it does

Analyzes unfiled papers and creates hierarchical collections with tags. Works directly with local Zotero database - no API keys or cloud sync required.

## Installation

Install as a UV tool for global access:

```bash
# Install from local directory
uv tool install .

# Or install directly from git
uv tool install git+https://github.com/yourusername/research-clerk.git

# Or run without installing
uvx --from . research-clerk
```

Zotero database auto-detected at `~/Zotero/zotero.sqlite`. Set `ZOTERO_DATA_DIR` for custom locations.

## Usage

### Categorize unfiled items

```bash
# Dry-run: analyze and save suggestions
research-clerk --batch-size 10

# Apply saved suggestions (path shown in output)
research-clerk --apply-suggestions ~/.local/share/research-clerk/suggestions.json
```

### Reorganize existing structure

```bash
# Dry-run: analyze and suggest reorganization
research-clerk --reorganize

# Apply saved reorganization
research-clerk --apply-reorganization ~/.local/share/research-clerk/reorganization.json
```

### Options

```bash
# Use custom output directory
research-clerk --output-dir ./my-suggestions --batch-size 10

# Get help
research-clerk --help
```

Suggestions are saved to `~/.local/share/research-clerk/` by default (XDG compliant).

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
