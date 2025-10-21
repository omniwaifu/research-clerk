# Changes from original design

## What changed

**Original plan:** Use pyzotero + web API (requires API keys)

**Actual implementation:** Direct sqlite access to local zotero database

## Why

- Zotero 7 local API is read-only (no writes yet)
- pyzotero can't do local writes either
- You wanted local-only, no sync

## What this means

### Before (planned):
- Need zotero.org account
- Need API key
- Need to enable sync
- API rate limits (120 req/min)
- Network required

### Now (actual):
- No setup needed
- Auto-detects database
- No network required
- No rate limits
- Direct sqlite access

## Safety improvements

**Automatic backups:**
- Created before any write
- Timestamped in `~/Zotero/backups/`
- Easy to restore if anything goes wrong

**Zotero running check:**
- Prevents corruption by detecting if zotero is open
- Uses exclusive lock test
- Only applies to `--apply` mode (writes)

**Read-only dry-run:**
- Can analyze while zotero is running
- Opens DB in read-only mode
- Safe to use anytime

**Transactions:**
- All changes are atomic
- Rollback on any error
- No partial modifications

## Risks

**Schema changes:**
- If zotero updates database schema, we may need to update queries
- Current implementation matches zotero 7 schema
- Low risk (schema is stable)

**Direct DB access:**
- Bypasses zotero's validation
- Mitigated by: careful schema adherence, backups, transactions
- Alternative would be waiting for zotero to implement local API writes (timeline unknown)

## Trade-offs

✅ **Pros:**
- Zero setup (no API keys)
- Works offline
- No sync required
- Faster (no network)
- Full control

⚠️ **Cons:**
- Must close zotero for writes
- Schema coupling (if zotero changes schema, we need updates)
- No built-in validation from zotero API

**Verdict:** Worth it for local-only use case.
