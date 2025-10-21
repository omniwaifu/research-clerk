#!/usr/bin/env python3
"""Command-line interface for research-clerk."""
import anyio
import sys
from pathlib import Path
from research_clerk.categorizer import categorize_unfiled
from research_clerk.apply_suggestions import apply_suggestions
from research_clerk.reorganizer import reorganize_collections
from research_clerk.apply_reorganization import apply_reorganization


async def main():
    """Main entry point for research-clerk CLI."""
    # Parse flags
    apply_suggestions_file = None
    apply_reorganization_file = None
    batch_size = None
    reorganize_mode = False

    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--apply-suggestions" and i + 1 < len(sys.argv):
            apply_suggestions_file = Path(sys.argv[i + 1])
            i += 2
        elif arg == "--apply-reorganization" and i + 1 < len(sys.argv):
            apply_reorganization_file = Path(sys.argv[i + 1])
            i += 2
        elif arg == "--batch-size" and i + 1 < len(sys.argv):
            batch_size = int(sys.argv[i + 1])
            i += 2
        elif arg == "--reorganize":
            reorganize_mode = True
            i += 1
        else:
            i += 1

    # Handle apply modes first (don't run agent, just apply saved suggestions)
    if apply_suggestions_file:
        print("🚀 APPLY SAVED SUGGESTIONS MODE")
        print(f"   Loading from: {apply_suggestions_file}\n")
        try:
            apply_suggestions(apply_suggestions_file)
        except KeyboardInterrupt:
            print("\n\nCancelled by user")
            sys.exit(1)
        except Exception as e:
            print(f"\n\nError: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        return

    if apply_reorganization_file:
        print("🚀 APPLY SAVED REORGANIZATION MODE")
        print(f"   Loading from: {apply_reorganization_file}\n")
        try:
            apply_reorganization(apply_reorganization_file)
        except KeyboardInterrupt:
            print("\n\nCancelled by user")
            sys.exit(1)
        except Exception as e:
            print(f"\n\nError: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        return

    # Reorganize mode vs categorize mode
    if reorganize_mode:
        # Reorganization mode
        dry_run = "--apply" not in sys.argv

        if dry_run:
            print("🔍 REORGANIZE DRY RUN MODE")
            print("   Will analyze existing collections and suggest reorganizations")
            print("   Suggestions will be saved to reorganization.json")
            if batch_size:
                print(f"   Processing first {batch_size} items")
            print("   Run with: python cli.py --apply-reorganization reorganization.json\n")
        else:
            print("⚠️  REORGANIZE APPLY MODE")
            print("   Will move items and reorganize collection structure")
            if batch_size:
                print(f"   Processing first {batch_size} items")
            print("   Press Ctrl+C to cancel\n")

        try:
            await reorganize_collections(dry_run=dry_run, batch_size=batch_size)
        except KeyboardInterrupt:
            print("\n\nCancelled by user")
            sys.exit(1)
        except Exception as e:
            print(f"\n\nError: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    else:
        # Original categorization mode
        dry_run = "--apply" not in sys.argv

        if dry_run:
            print("🔍 DRY RUN MODE")
            print("   Will analyze and suggest categorizations")
            print("   Suggestions will be saved to suggestions.json")
            if batch_size:
                print(f"   Processing first {batch_size} items")
            print("   Run with: python cli.py --apply-suggestions suggestions.json\n")
        else:
            print("⚠️  APPLY MODE")
            print("   Will create collections and categorize items")
            if batch_size:
                print(f"   Processing first {batch_size} items")
            print("   Press Ctrl+C to cancel\n")

        try:
            await categorize_unfiled(dry_run=dry_run, batch_size=batch_size)
        except KeyboardInterrupt:
            print("\n\nCancelled by user")
            sys.exit(1)
        except Exception as e:
            print(f"\n\nError: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)


if __name__ == "__main__":
    anyio.run(main)
