# research-clerk

Uses Claude to categorize papers in your Zotero library. Reads your local database directly.

Give it unfiled papers, it creates collections and tags them. Can also reorganize existing collections if you want to refactor your taxonomy.

## Install

```bash
uv tool install .

# or from git
uv tool install git+https://github.com/yourusername/research-clerk.git
```

Finds your Zotero database at `~/Zotero/zotero.sqlite`. If it's somewhere else, set `ZOTERO_DATA_DIR`.

## How to use

Run dry-run first (outputs JSON), review it, apply if it looks good:

```bash
# analyze 10 unfiled papers
research-clerk --batch-size 10

# check the suggestions
cat ~/.local/share/research-clerk/suggestions.json

# apply them
research-clerk --apply-suggestions ~/.local/share/research-clerk/suggestions.json
```

Or reorganize stuff that's already filed:

```bash
research-clerk --reorganize
research-clerk --apply-reorganization ~/.local/share/research-clerk/reorganization.json
```

Output goes to `~/.local/share/research-clerk/` by default. Change it with `--output-dir`.

## How it works

Talks to your SQLite database via an in-process MCP server. Agent can list papers, read abstracts, create collections, add tags.

Enforces some rules: max 3 levels deep, 2-5 tags per paper, won't create subcategories until there's 3+ papers to justify it. Reuses existing collections when possible.

Dry-run is read-only, works with Zotero open. Apply mode backs up your database first and refuses to run if Zotero is running. Uses transactions so errors rollback cleanly. Never deletes anything.
