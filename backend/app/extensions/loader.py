"""Extension loader for The Kai Seeker (解を求める者).

Auto-discovery loader for user extensions (Python tools + Markdown skills).

Scans two locations:
1. Built-in:  app/skills/builtin/       (Markdown skills shipped with the project)
2. User-defined: user_extensions/tools/  (Python tools)
                 user_extensions/skills/ (Markdown skills)

This file is part of The Kai Seeker, licensed under AGPL-3.0.
Source: https://github.com/Myyura/the_kai_seeker

Python tools are loaded via importlib. Each .py file should contain exactly one
BaseTool subclass, which is auto-discovered and registered.

Markdown skills are loaded via parse_skill_file. Each .md file or SKILL.md in
a subdirectory is parsed and registered.
"""

import importlib
import importlib.util
import inspect
import logging
import sys
from pathlib import Path

from app.skills.registry import skill_registry
from app.tools.base import BaseTool
from app.tools.registry import tool_registry

logger = logging.getLogger(__name__)


def _load_python_tools(directory: Path) -> int:
    """Import .py files from directory and register any BaseTool subclasses found."""
    if not directory.exists():
        return 0

    count = 0
    for py_file in sorted(directory.glob("*.py")):
        if py_file.name.startswith("_"):
            continue

        module_name = f"user_ext_tool_{py_file.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if spec is None or spec.loader is None:
                logger.warning("Cannot load %s: invalid module spec", py_file)
                continue

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            for _name, obj in inspect.getmembers(module, inspect.isclass):
                if (
                    issubclass(obj, BaseTool)
                    and obj is not BaseTool
                    and obj.__module__ == module_name
                ):
                    try:
                        instance = obj()
                        tool_registry.register(instance)
                        count += 1
                        logger.info("Loaded user tool '%s' from %s", instance.name, py_file.name)
                    except Exception as e:
                        logger.error("Failed to instantiate tool from %s: %s", py_file.name, e)

        except Exception as e:
            logger.error("Failed to load user tool %s: %s", py_file.name, e)

    return count


def reload_all_extensions(base_dir: Path) -> dict:
    """Clear user extensions and reload everything from disk.

    Builtin tools (registered via register_builtin_tools) are preserved.
    Builtin and user skills are reloaded. User tools are reloaded.
    """
    skill_registry.clear()

    user_tool_names = [
        name for name, tool in list(tool_registry._tools.items())
        if getattr(tool, "__module__", "").startswith("user_ext_tool_")
    ]
    for name in user_tool_names:
        del tool_registry._tools[name]

    for mod_name in list(sys.modules.keys()):
        if mod_name.startswith("user_ext_tool_"):
            del sys.modules[mod_name]

    return load_all_extensions(base_dir)


def load_all_extensions(base_dir: Path) -> dict:
    """Load all extensions from builtin and user directories.

    Args:
        base_dir: The backend root directory (where app/ and user_extensions/ live).

    Returns:
        Summary dict with counts.
    """
    summary = {
        "builtin_skills": 0,
        "user_tools": 0,
        "user_skills": 0,
    }

    builtin_skills_dir = base_dir / "app" / "skills" / "builtin"
    summary["builtin_skills"] = skill_registry.load_directory(builtin_skills_dir, source="builtin")

    user_ext_dir = base_dir / "user_extensions"

    user_tools_dir = user_ext_dir / "tools"
    summary["user_tools"] = _load_python_tools(user_tools_dir)

    user_skills_dir = user_ext_dir / "skills"
    summary["user_skills"] = skill_registry.load_directory(user_skills_dir, source="user")

    logger.info(
        "Extensions loaded: %d builtin skills, %d user tools, %d user skills",
        summary["builtin_skills"],
        summary["user_tools"],
        summary["user_skills"],
    )

    return summary
