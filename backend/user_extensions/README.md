# User Extensions

Drop your custom **Tools** (Python) and **Skills** (Markdown) here.
They are auto-discovered on backend startup.

## Directory Structure

```
user_extensions/
  tools/           Python tools (executable capabilities)
    my_tool.py
  skills/          Markdown skills (knowledge & behavior guides)
    my_skill.md
```

## Creating a Tool (Python)

A Tool gives the LLM the ability to **do things** — fetch web pages, query APIs,
run calculations, etc.

Create a `.py` file in `tools/` with a class that inherits `BaseTool`:

```python
from pydantic import BaseModel, Field
from app.tools.base import BaseTool, ToolResult

class MyTool(BaseTool):
    name = "my_tool"
    description = "What this tool does, and when the LLM should use it."

    class Args(BaseModel):
        query: str = Field(description="The search query")
        limit: int = Field(default=10, ge=1, le=100, description="Max results")

    async def execute(self, args: Args) -> ToolResult:
        # Your logic here — can use httpx, file I/O, etc.
        return ToolResult(success=True, data=f"Results for: {args.query}")
```

Key points:
- `name` and `description` are shown to the LLM in the system prompt
- `Args` uses Pydantic for automatic validation — bad arguments from the LLM
  are caught and returned as error messages so the LLM can self-correct
- `execute` receives a validated `Args` instance

## Creating a Skill (Markdown)

A Skill injects **domain knowledge and behavioral guidelines** into the LLM's
system prompt when the user's message matches certain triggers.

Create a `.md` file in `skills/` with YAML frontmatter:

```markdown
---
name: my-skill
description: What this skill provides and when to activate it.
trigger: keyword1,keyword2,关键词
allowed-tools: web_fetch search_questions
metadata:
  author: your-name
  version: "1.0"
---

# My Skill Title

Instructions and knowledge for the LLM...

## How to handle X

1. First do this
2. Then do that
```

### Frontmatter Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Unique identifier (lowercase, hyphens) |
| `description` | Yes | When and why to activate this skill |
| `trigger` | No | Comma-separated keywords that activate the skill. If empty, skill is always active |
| `allowed-tools` | No | Space-separated tool names this skill recommends using |
| `metadata` | No | Arbitrary key-value pairs (author, version, tags) |

### How Activation Works

When a user sends a message:
1. The system checks each skill's `trigger` keywords against the message
2. Matching skills have their full Markdown body injected into the system prompt
3. The LLM then has access to that domain knowledge for its response

### Tips

- Keep skills focused — one skill per topic
- Be specific in trigger keywords to avoid always-on activation
- Use `allowed-tools` to hint which tools complement the skill
- The body content has no format restrictions — write whatever helps the LLM

## Notes

- This directory is git-ignored — your custom extensions won't conflict with upstream updates
- Restart the backend to load new extensions (hot reload will also pick them up in dev mode)
- A broken extension only affects itself — the rest of the system continues working
