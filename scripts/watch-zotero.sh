#!/usr/bin/env bash
#
# watch-zotero.sh - Monitor Zotero for new unfiled papers and auto-categorize
#
# This script polls the Zotero database for unfiled items and automatically
# categorizes new papers using research-clerk.
#

set -euo pipefail

# Configuration
POLL_INTERVAL="${POLL_INTERVAL:-60}"  # seconds between checks
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/research-clerk"
TIMESTAMP_FILE="$DATA_DIR/last_unfiled_timestamp"
LOG_FILE="$DATA_DIR/watch.log"
SUGGESTIONS_FILE="$DATA_DIR/suggestions.json"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Show help
show_help() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS]

Monitor Zotero database for new unfiled papers and automatically categorize them.

OPTIONS:
    -h, --help              Show this help message
    -i, --interval SECONDS  Polling interval (default: 60)
    -v, --verbose           Enable verbose logging to console

ENVIRONMENT VARIABLES:
    POLL_INTERVAL           Override default polling interval
    ZOTERO_DATA_DIR         Override Zotero database location

WORKFLOW:
    1. Poll Zotero database every ${POLL_INTERVAL}s for new unfiled items (read-only)
    2. Track last-seen timestamp in $TIMESTAMP_FILE
    3. When new unfiled items detected (items added after last timestamp):
       - Generate categorization suggestions
       - Gracefully shut down Zotero
       - Apply suggestions to database
       - Restart Zotero
       - Send desktop notification
       - Update timestamp to newest processed item

LOGS:
    $LOG_FILE

NOTES:
    - First run sets baseline to current max timestamp (won't process existing items)
    - Handles edge cases: manual filing, deletions, multiple simultaneous additions
    - To reset and process all unfiled items: rm $TIMESTAMP_FILE

REQUIREMENTS:
    - research-clerk installed and in PATH
    - notify-send (libnotify) for desktop notifications
    - Zotero installed

EXAMPLES:
    # Start monitoring with default 60s interval
    $(basename "$0")

    # Check every 30 seconds
    $(basename "$0") --interval 30

    # Verbose mode
    $(basename "$0") --verbose

EOF
}

# Logging function
log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    # Always log to file
    echo "[$timestamp] [$level] $message" >> "$LOG_FILE"

    # Console output
    case "$level" in
        INFO)
            echo -e "${BLUE}[INFO]${NC} $message"
            ;;
        SUCCESS)
            echo -e "${GREEN}[SUCCESS]${NC} $message"
            ;;
        WARN)
            echo -e "${YELLOW}[WARN]${NC} $message"
            ;;
        ERROR)
            echo -e "${RED}[ERROR]${NC} $message"
            ;;
        *)
            echo "$message"
            ;;
    esac
}

# Send desktop notification
notify() {
    local title="$1"
    local message="$2"
    local urgency="${3:-normal}"

    if command -v notify-send >/dev/null 2>&1; then
        notify-send -u "$urgency" "$title" "$message"
    fi
}

# Get max timestamp of unfiled items (read-only query)
get_max_unfiled_timestamp() {
    python3 -c '
import sys
try:
    from research_clerk.backends.local_sqlite import LocalSQLiteBackend
    from research_clerk.config import find_zotero_database

    db_path = find_zotero_database()
    backend = LocalSQLiteBackend(db_path)
    with backend.connect(read_only=True):
        max_date = backend.get_max_unfiled_date()
        if max_date:
            print(max_date)
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
'
}

# Get new unfiled items since timestamp (read-only query)
get_new_unfiled_items() {
    local since_timestamp="$1"
    python3 -c '
import sys
import json
try:
    from research_clerk.backends.local_sqlite import LocalSQLiteBackend
    from research_clerk.config import find_zotero_database

    since = sys.argv[1] if len(sys.argv) > 1 else ""

    db_path = find_zotero_database()
    backend = LocalSQLiteBackend(db_path)
    with backend.connect(read_only=True):
        if since:
            items = backend.list_unfiled_items_since(since)
        else:
            items = backend.list_unfiled_items()
        print(json.dumps(items))
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
' "$since_timestamp"
}

# Checkpoint WAL file to ensure all changes are in main database
checkpoint_wal() {
    log INFO "Checkpointing WAL file..."
    python3 -c '
import sys
import sqlite3
try:
    from research_clerk.config import find_zotero_database

    db_path = find_zotero_database()
    # Connect without read-only mode to checkpoint
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    print("WAL checkpointed", file=sys.stderr)
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
' 2>>"$LOG_FILE"

    if [ $? -eq 0 ]; then
        log SUCCESS "WAL checkpointed"
        return 0
    else
        log WARN "Failed to checkpoint WAL"
        return 1
    fi
}

# Kill Zotero gracefully
kill_zotero() {
    log INFO "Shutting down Zotero..."

    if ! pgrep -x zotero >/dev/null; then
        log INFO "Zotero is not running"
        return 0
    fi

    # Try graceful shutdown first
    pkill -TERM zotero || true

    # Wait up to 10 seconds for graceful shutdown
    for i in {1..10}; do
        if ! pgrep -x zotero >/dev/null; then
            log SUCCESS "Zotero shut down gracefully"
            # Wait a moment for file handles to close
            sleep 2
            # Checkpoint the WAL to ensure all Zotero's changes are in main DB
            checkpoint_wal
            return 0
        fi
        sleep 1
    done

    # Force kill if still running
    log WARN "Forcing Zotero shutdown..."
    pkill -9 zotero || true
    sleep 2

    if pgrep -x zotero >/dev/null; then
        log ERROR "Failed to kill Zotero"
        return 1
    fi

    log SUCCESS "Zotero terminated"
    # Checkpoint the WAL
    checkpoint_wal
    return 0
}

# Start Zotero
start_zotero() {
    log INFO "Starting Zotero..."

    # Try common Zotero locations
    if command -v zotero >/dev/null 2>&1; then
        nohup zotero >/dev/null 2>&1 &
    elif [ -f "/usr/bin/zotero" ]; then
        nohup /usr/bin/zotero >/dev/null 2>&1 &
    elif [ -f "$HOME/.local/bin/zotero" ]; then
        nohup "$HOME/.local/bin/zotero" >/dev/null 2>&1 &
    else
        log WARN "Could not find Zotero executable - please start manually"
        notify "Zotero Auto-Categorizer" "Please start Zotero manually" "normal"
        return 1
    fi

    sleep 3

    if pgrep -x zotero >/dev/null; then
        log SUCCESS "Zotero started"
        return 0
    else
        log WARN "Zotero may not have started - check manually"
        return 1
    fi
}

# Process new unfiled items
process_new_items() {
    local new_items_json="$1"
    local count=$(echo "$new_items_json" | python3 -c "import sys, json; print(len(json.load(sys.stdin)))")

    if [ "$count" -eq 0 ]; then
        log INFO "No new items to process"
        return 0
    fi

    log INFO "Processing $count new unfiled item(s)..."

    # Log the items we're about to process
    echo "$new_items_json" | python3 -c '
import sys, json
items = json.load(sys.stdin)
for item in items:
    title = item.get("title", "Untitled")
    date = item.get("dateAdded", "unknown")
    print(f"  - {title} (added: {date})", file=sys.stderr)
' 2>> "$LOG_FILE"

    # Step 1: Delete old suggestions file to avoid applying stale data
    if [ -f "$SUGGESTIONS_FILE" ]; then
        log INFO "Removing stale suggestions file..."
        rm "$SUGGESTIONS_FILE"
    fi

    # Step 2: Kill Zotero before generating suggestions
    # (The MCP tools still have DB lock issues even with immutable mode)
    if ! kill_zotero; then
        log ERROR "Failed to shut down Zotero"
        notify "Zotero Auto-Categorizer" "Failed to shut down Zotero" "critical"
        return 1
    fi

    # Step 3: Generate suggestions (with Zotero closed)
    log INFO "Generating categorization suggestions..."
    if research-clerk --batch-size "$count" >> "$LOG_FILE" 2>&1; then
        log SUCCESS "Suggestions generated"
    else
        log ERROR "Failed to generate suggestions"
        notify "Zotero Auto-Categorizer" "Failed to generate suggestions" "critical"
        start_zotero  # Try to restart even if generation failed
        return 1
    fi

    # Check if suggestions file exists and has content
    if [ ! -f "$SUGGESTIONS_FILE" ]; then
        log WARN "No suggestions file generated - nothing to apply"
        start_zotero
        return 0
    fi

    # Step 4: Apply suggestions (Zotero already closed from step 2)
    log INFO "Applying categorization suggestions..."
    if research-clerk --apply-suggestions "$SUGGESTIONS_FILE" >> "$LOG_FILE" 2>&1; then
        log SUCCESS "Suggestions applied successfully"
    else
        log ERROR "Failed to apply suggestions"
        notify "Zotero Auto-Categorizer" "Failed to apply categorizations" "critical"
        start_zotero  # Try to restart even if apply failed
        return 1
    fi

    # Step 5: Restart Zotero
    start_zotero

    # Step 6: Notify success
    log SUCCESS "Auto-categorized $count new paper(s)"
    notify "Zotero Auto-Categorizer" "Categorized $count new paper(s)" "normal"

    return 0
}

# Main monitoring loop
monitor() {
    log INFO "Starting Zotero monitor (polling every ${POLL_INTERVAL}s)..."
    log INFO "Logs: $LOG_FILE"

    # Initialize timestamp file if it doesn't exist
    if [ ! -f "$TIMESTAMP_FILE" ]; then
        log INFO "First run - initializing baseline timestamp..."
        max_timestamp=$(get_max_unfiled_timestamp 2>>"$LOG_FILE" || echo "")
        if [ -n "$max_timestamp" ]; then
            echo "$max_timestamp" > "$TIMESTAMP_FILE"
            log INFO "Baseline timestamp: $max_timestamp (will not process existing items)"
        else
            log WARN "Could not get max timestamp (database may be locked) - starting from epoch"
            echo "1970-01-01 00:00:00" > "$TIMESTAMP_FILE"
        fi
    fi

    while true; do
        # Read last known timestamp
        last_timestamp=$(cat "$TIMESTAMP_FILE" 2>/dev/null || echo "1970-01-01 00:00:00")

        # Get new unfiled items since last timestamp
        new_items_json=$(get_new_unfiled_items "$last_timestamp" 2>>"$LOG_FILE")

        if [ $? -ne 0 ]; then
            log ERROR "Failed to query Zotero database"
            sleep "$POLL_INTERVAL"
            continue
        fi

        # Count new items
        new_count=$(echo "$new_items_json" | python3 -c "import sys, json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")

        if [ "$new_count" -gt 0 ]; then
            log INFO "Detected $new_count new unfiled item(s)"

            if process_new_items "$new_items_json"; then
                # Update timestamp to max of newly processed items
                new_max_timestamp=$(echo "$new_items_json" | python3 -c '
import sys, json
items = json.load(sys.stdin)
if items:
    max_date = max(item.get("dateAdded", "") for item in items)
    print(max_date)
' 2>/dev/null)

                if [ -n "$new_max_timestamp" ]; then
                    echo "$new_max_timestamp" > "$TIMESTAMP_FILE"
                    log INFO "Updated baseline timestamp to: $new_max_timestamp"
                fi
            else
                log ERROR "Processing failed - will retry next cycle"
            fi
        else
            log INFO "No new unfiled items (baseline: $last_timestamp)"
        fi

        # Wait for next poll
        sleep "$POLL_INTERVAL"
    done
}

# Parse arguments
VERBOSE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -i|--interval)
            POLL_INTERVAL="$2"
            shift 2
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Ensure data directory exists
mkdir -p "$DATA_DIR"

# Check dependencies
if ! command -v research-clerk >/dev/null 2>&1; then
    echo "ERROR: research-clerk not found in PATH"
    echo "Install with: uv tool install /path/to/research-clerk"
    exit 1
fi

if ! command -v notify-send >/dev/null 2>&1; then
    echo "WARN: notify-send not found - desktop notifications disabled"
fi

# Start monitoring
monitor
