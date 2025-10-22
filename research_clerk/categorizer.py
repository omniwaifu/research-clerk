"""Agent logic for categorizing Zotero papers."""
import json
import re
from pathlib import Path
from claude_agent_sdk import create_sdk_mcp_server, ClaudeSDKClient, ClaudeAgentOptions, AssistantMessage, TextBlock
from .tools import ALL_TOOLS
from .prompts import CATEGORIZER_PROMPT


async def categorize_unfiled(dry_run: bool = True, batch_size: int = None, output_dir: Path = None):
    """
    Categorize unfiled papers in the Zotero library.

    Args:
        dry_run: If True, only analyzes and suggests without making changes.
                 If False, actually creates collections and categorizes items.
        batch_size: If set, only process first N items. Useful for incremental runs.
        output_dir: Directory to save suggestion files. Defaults to current directory.
    """
    if output_dir is None:
        output_dir = Path.cwd()
    # Create in-process MCP server with our tools
    server = create_sdk_mcp_server(
        name="zotero-tools",
        version="0.1.0",
        tools=ALL_TOOLS
    )
    
    # Configure allowed tools based on dry-run mode
    if dry_run:
        # Dry-run: only allow read operations
        allowed_tools = [
            "mcp__zotero__list_unfiled_items",
            "mcp__zotero__get_item_details",
            "mcp__zotero__list_collections",
        ]
    else:
        # Apply mode: enable all tools including write operations
        allowed_tools = [
            "mcp__zotero__list_unfiled_items",
            "mcp__zotero__get_item_details",
            "mcp__zotero__list_collections",
            "mcp__zotero__create_collection",
            "mcp__zotero__add_to_collection",
            "mcp__zotero__add_tags_to_item",
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
Categorize unfiled papers in the library.{batch_instruction}

Process:
1. List unfiled items
2. Check existing collection structure
3. For each unfiled item (up to {batch_size if batch_size else 'all'} items):
   - Get full details (especially abstract)
   - Analyze content and decide on categorization
   - Determine appropriate collection hierarchy (max 3 levels)
   - Determine appropriate tags (2-5 tags)
   - Explain your reasoning
   - Apply categorization (create collections if needed, add item, add tags)

Show me your reasoning for each categorization decision.
"""
    
    if dry_run:
        prompt += """

DRY RUN MODE: Only analyze and suggest categorizations. Do NOT create collections or modify items.

IMPORTANT: At the end, output a JSON block with ALL suggestions in this exact format:
```json
{
  "items": [
    {
      "item_key": "ABCD1234",
      "title": "Paper Title",
      "collection_path": "Field/Subfield/Topic",
      "tags": ["tag1", "tag2"],
      "reasoning": "Brief explanation"
    }
  ]
}
```

For each paper:
- Determine collection path (max 3 levels, e.g. "Computer Science/AI/NLP")
- Choose 2-5 relevant tags
- Explain reasoning
Then output the final JSON block with ALL items.
"""
    else:
        prompt += """

APPLY MODE: Actually create the collections and categorize the items.
Create collections as needed (parents first), then add items and tags.
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
                    from .apply_suggestions import validate_suggestions
                    errors = validate_suggestions(suggestions)
                    if errors:
                        print("\n\n✗ Agent output failed validation:")
                        for error in errors:
                            print(f"   - {error}")
                        print("\n   Suggestions NOT saved. Agent may need to retry.")
                        return

                    # Save to file
                    output_file = output_dir / "suggestions.json"
                    with open(output_file, 'w') as f:
                        json.dump(suggestions, f, indent=2)

                    print(f"\n\n✓ Saved {len(suggestions.get('items', []))} suggestions to {output_file}")
                    print(f"   Run: research-clerk --apply-suggestions {output_file}")
                except json.JSONDecodeError as e:
                    print(f"\n\n✗ Failed to parse JSON: {e}")
                    print("   Agent output may not be in correct format")
            else:
                print("\n\n⚠️  No JSON block found in agent output")
                print("   Agent may not have finished or formatted output incorrectly")
