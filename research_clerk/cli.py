#!/usr/bin/env python3
"""Command-line interface for research-clerk."""
import argparse
import sys
from pathlib import Path
import anyio
from .categorizer import categorize_unfiled
from .apply_suggestions import apply_suggestions
from .reorganizer import reorganize_collections
from .apply_reorganization import apply_reorganization


def get_default_output_dir() -> Path:
    """Get default output directory (XDG compliant)."""
    xdg_data_home = Path.home() / ".local" / "share"
    return xdg_data_home / "research-clerk"


def normalize_model_name(model: str) -> str:
    """Normalize model name to full form."""
    if model == "haiku":
        return "claude-haiku-4-5"
    elif model == "sonnet":
        return "claude-sonnet-4-5"
    return model


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="research-clerk",
        description="AI-powered categorization for Zotero libraries using Claude Agent SDK",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry-run categorization (analyze and save suggestions)
  research-clerk --batch-size 10

  # Apply saved suggestions
  research-clerk --apply-suggestions suggestions.json

  # Reorganize existing structure
  research-clerk --reorganize

  # Apply saved reorganization
  research-clerk --apply-reorganization reorganization.json

  # Use custom output directory
  research-clerk --output-dir ./my-suggestions --batch-size 5
        """
    )

    # Mode selection (mutually exclusive)
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--apply-suggestions",
        metavar="FILE",
        type=Path,
        help="Apply saved suggestions from FILE"
    )
    mode_group.add_argument(
        "--apply-reorganization",
        metavar="FILE",
        type=Path,
        help="Apply saved reorganization from FILE"
    )
    mode_group.add_argument(
        "--reorganize",
        action="store_true",
        help="Reorganize existing collection structure (dry-run mode)"
    )

    # Options
    parser.add_argument(
        "--batch-size",
        type=int,
        metavar="N",
        help="Process only first N items (useful for incremental runs)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=get_default_output_dir(),
        help=f"Directory to save suggestion files (default: {get_default_output_dir()})"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="claude-haiku-4-5",
        choices=["claude-haiku-4-5", "claude-sonnet-4-5", "haiku", "sonnet"],
        help="Claude model to use (default: claude-haiku-4-5)"
    )

    return parser.parse_args()


async def async_main():
    """Async main entry point for research-clerk CLI."""
    args = parse_args()

    # Handle apply modes first (don't run agent, just apply saved suggestions)
    if args.apply_suggestions:
        print("APPLY SAVED SUGGESTIONS MODE")
        print(f"   Loading from: {args.apply_suggestions}\n")
        try:
            apply_suggestions(args.apply_suggestions)
        except KeyboardInterrupt:
            print("\n\nCancelled by user")
            sys.exit(1)
        except Exception as e:
            print(f"\n\nError: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        return

    if args.apply_reorganization:
        print("APPLY SAVED REORGANIZATION MODE")
        print(f"   Loading from: {args.apply_reorganization}\n")
        try:
            apply_reorganization(args.apply_reorganization)
        except KeyboardInterrupt:
            print("\n\nCancelled by user")
            sys.exit(1)
        except Exception as e:
            print(f"\n\nError: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        return

    # Ensure output directory exists
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Normalize model name
    model = normalize_model_name(args.model)

    # Reorganize mode vs categorize mode
    if args.reorganize:
        # Reorganization mode (always dry-run)
        print("REORGANIZE DRY RUN MODE")
        print("   Will analyze existing collections and suggest reorganizations")
        print(f"   Suggestions will be saved to {args.output_dir / 'reorganization.json'}")
        print(f"   Using model: {model}")
        if args.batch_size:
            print(f"   Processing first {args.batch_size} items")
        print(f"   Run with: research-clerk --apply-reorganization {args.output_dir / 'reorganization.json'}\n")

        try:
            await reorganize_collections(
                dry_run=True,
                batch_size=args.batch_size,
                output_dir=args.output_dir,
                model=model
            )
        except KeyboardInterrupt:
            print("\n\nCancelled by user")
            sys.exit(1)
        except Exception as e:
            print(f"\n\nError: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    else:
        # Original categorization mode (always dry-run)
        print("DRY RUN MODE")
        print("   Will analyze and suggest categorizations")
        print(f"   Suggestions will be saved to {args.output_dir / 'suggestions.json'}")
        print(f"   Using model: {model}")
        if args.batch_size:
            print(f"   Processing first {args.batch_size} items")
        print(f"   Run with: research-clerk --apply-suggestions {args.output_dir / 'suggestions.json'}\n")

        try:
            await categorize_unfiled(
                dry_run=True,
                batch_size=args.batch_size,
                output_dir=args.output_dir,
                model=model
            )
        except KeyboardInterrupt:
            print("\n\nCancelled by user")
            sys.exit(1)
        except Exception as e:
            print(f"\n\nError: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)


def main():
    """Main entry point for research-clerk CLI."""
    anyio.run(async_main)


if __name__ == "__main__":
    main()
