"""Agent logic for reorganizing Zotero collection structure."""
import json
import re
from pathlib import Path
from claude_agent_sdk import create_sdk_mcp_server, ClaudeSDKClient, ClaudeAgentOptions, AssistantMessage, TextBlock
from .tools import REORGANIZE_TOOLS
from .prompts import CATEGORIZER_PROMPT


async def reorganize_collections(dry_run: bool = True, batch_size: int = None, output_dir: Path = None):
    """
    Analyze existing collection structure and suggest reorganizations.

    Args:
        dry_run: If True, only analyzes and suggests without making changes.
                 If False, actually moves items and creates new collections.
        batch_size: If set, only process first N items. Useful for incremental runs.
        output_dir: Directory to save suggestion files. Defaults to current directory.
    """
    if output_dir is None:
        output_dir = Path.cwd()
    # Create in-process MCP server with reorganization tools
    server = create_sdk_mcp_server(
        name="zotero-tools",
        version="0.1.0",
        tools=REORGANIZE_TOOLS
    )

    # Configure allowed tools based on dry-run mode
    if dry_run:
        # Dry-run: only allow read operations
        allowed_tools = [
            "mcp__zotero__list_filed_items",
            "mcp__zotero__get_item_details",
            "mcp__zotero__get_item_collections",
            "mcp__zotero__list_collections",
        ]
    else:
        # Apply mode: enable all tools including writes
        allowed_tools = [
            "mcp__zotero__list_filed_items",
            "mcp__zotero__get_item_details",
            "mcp__zotero__get_item_collections",
            "mcp__zotero__list_collections",
            "mcp__zotero__create_collection",
            "mcp__zotero__add_to_collection",
            "mcp__zotero__remove_from_collection",
        ]

    # Configure agent options
    options = ClaudeAgentOptions(
        mcp_servers={"zotero": server},
        allowed_tools=allowed_tools,
        system_prompt=CATEGORIZER_PROMPT,
        max_turns=50,  # Allow multiple rounds of exploration
    )

    # Build the prompt
    batch_instruction = ""
    if batch_size:
        batch_instruction = f"\n\nIMPORTANT: Only process the first {batch_size} items. Skip the rest.\n"

    prompt = f"""
Analyze the existing Zotero collection structure and suggest reorganizations.{batch_instruction}

Process:
1. List filed items (items already in collections)
2. Check existing collection structure
3. For each filed item (up to {batch_size if batch_size else 'all'} items):
   - Get full details (especially abstract)
   - Get current collection path(s)
   - Analyze if it should be moved to a better location
   - Determine if new subcategories should be created based on clustering
   - Explain your reasoning

REORGANIZATION RULES:
- Create subcategories when you see 3+ related papers in a parent category
- Move papers to more specific subcategories when appropriate
- Consolidate overly fragmented structure
- Max 3 levels deep (Field/Subfield/Topic)

Show me your reasoning for each reorganization decision.
"""

    if dry_run:
        prompt += """

DRY RUN MODE: Only analyze and suggest reorganizations. Do NOT move items or create collections.

IMPORTANT: At the end, output a JSON block with ALL suggestions in this exact format:
```json
{
  "moves": [
    {
      "item_key": "ABCD1234",
      "title": "Paper Title",
      "current_path": "Computer Science/AI",
      "new_path": "Computer Science/AI/Machine Learning",
      "reasoning": "Create ML subcategory - found 5 ML papers in AI"
    }
  ]
}
```

For each paper that should be moved:
- Specify current collection path
- Specify proposed new collection path (max 3 levels)
- Explain reasoning
Then output the final JSON block with ALL moves.
"""
    else:
        prompt += """

APPLY MODE: Actually move items and create the new collection structure.
Process moves by:
1. Creating new collections (parents first)
2. Adding items to new collections
3. Removing items from old collections
"""

    # Run the agent
    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt)

        # Collect responses
        all_text = []
        async for msg in client.receive_response():
            print(msg)
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        all_text.append(block.text)

        # If dry-run, extract and save JSON
        if dry_run:
            full_text = '\n'.join(all_text)

            # Find JSON block
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', full_text, re.DOTALL)
            if json_match:
                try:
                    suggestions = json.loads(json_match.group(1))

                    # Validate schema before saving
                    from .apply_reorganization import validate_reorganization
                    errors = validate_reorganization(suggestions)
                    if errors:
                        print("\n\n✗ Agent output failed validation:")
                        for error in errors:
                            print(f"   - {error}")
                        print("\n   Suggestions NOT saved. Agent may need to retry.")
                        return

                    # Save to file
                    output_file = output_dir / "reorganization.json"
                    with open(output_file, 'w') as f:
                        json.dump(suggestions, f, indent=2)

                    print(f"\n\n✓ Saved {len(suggestions.get('moves', []))} reorganization suggestions to {output_file}")
                    print(f"   Run: research-clerk --apply-reorganization {output_file}")
                except json.JSONDecodeError as e:
                    print(f"\n\n✗ Failed to parse JSON: {e}")
                    print("   Agent output may not be in correct format")
            else:
                print("\n\n⚠️  No JSON block found in agent output")
                print("   Agent may not have finished or formatted output incorrectly")
