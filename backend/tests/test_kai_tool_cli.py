import json
import os
import subprocess
import sys
from pathlib import Path


def test_kai_tool_cli_returns_structured_json(tmp_path) -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'kai-tool.db').as_posix()}"
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.tools.cli",
            "run",
            "echo",
            "--json",
            json.dumps({"message": "hi"}, ensure_ascii=False),
        ],
        cwd=backend_dir,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload == {"ok": True, "data": "Echo: hi"}
