import argparse
import asyncio
import json
import sys
from typing import Any

from app.bootstrap import initialize_runtime_environment
from app.tools.registry import tool_registry


async def _run_tool(tool_name: str, raw_json: str) -> int:
    await initialize_runtime_environment(ensure_db=True)
    try:
        args = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "error": f"Invalid JSON: {exc}"}, ensure_ascii=False))
        return 2
    if not isinstance(args, dict):
        print(json.dumps({"ok": False, "error": "Tool arguments must be a JSON object."}, ensure_ascii=False))
        return 2

    result = await tool_registry.execute(tool_name, **args)
    if result.success:
        data: Any = result.data
        print(json.dumps({"ok": True, "data": data}, ensure_ascii=False))
        return 0
    print(json.dumps({"ok": False, "error": result.error or "Unknown error"}, ensure_ascii=False))
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kai-tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a Kai tool by name.")
    run_parser.add_argument("tool_name")
    run_parser.add_argument("--json", dest="raw_json", required=True)

    args = parser.parse_args(argv)
    if args.command != "run":
        parser.error(f"Unsupported command: {args.command}")
    return asyncio.run(_run_tool(args.tool_name, args.raw_json))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
