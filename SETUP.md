# research-clerk setup guide

## step 1: install dependencies

```bash
cd /mnt/data/Code/research-clerk
uv sync
```

## step 2: that's it

no API keys, no configuration needed. the tool auto-detects your zotero database at:
- `~/Zotero/zotero.sqlite` (most common)
- `~/.zotero/zotero/zotero.sqlite`
- `~/snap/zotero-snap/common/Zotero/zotero.sqlite` (snap install)

if using custom location:
```bash
export ZOTERO_DATA_DIR=/path/to/your/zotero/data
```

## step 3: test it (dry-run)

```bash
python cli.py
```

**IMPORTANT:** Dry-run mode can run while zotero is open (read-only). It will:
1. list unfiled items in your library
2. analyze each paper's abstract/title
3. suggest collection hierarchy and tags
4. explain its reasoning

## step 4: apply changes

**CLOSE ZOTERO FIRST** to prevent database corruption, then:

```bash
python cli.py --apply
```

this will:
1. create a timestamped backup in `~/Zotero/backups/`
2. check that zotero isn't running (aborts if it is)
3. create collections and categorize items
4. use transactions (rollback on any error)

## safety features

- **auto-backup**: timestamped backup before any write
- **lock check**: aborts if zotero is running
- **transactions**: all-or-nothing (no partial changes)
- **read-only dry-run**: safe to run while zotero is open
- **no deletes**: only creates collections and adds items/tags

## troubleshooting

**"Zotero database not found"**
- check zotero is installed and has been run at least once
- set `ZOTERO_DATA_DIR` if using custom location

**"Zotero is running!"**
- this is a safety check for `--apply` mode
- close zotero before running with `--apply`
- dry-run mode works fine with zotero open

**agent creates weird collections**
- tune the prompt in `research_clerk/prompts.py`
- run dry-run first to see suggestions

**"database is locked"**
- zotero or another process has the DB open
- close zotero and retry

## how backups work

backups are created in `~/Zotero/backups/zotero_backup_YYYYMMDD_HHMMSS.sqlite`

to restore from backup:
1. close zotero
2. `cp ~/Zotero/backups/zotero_backup_*.sqlite ~/Zotero/zotero.sqlite`
3. restart zotero
