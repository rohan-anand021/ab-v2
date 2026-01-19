from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from sandbox.models import RunReport


class RunRecorder:
    def __init__(self, artifacts_dir: Path, stdout_limit: int = 8000, stderr_limit: int = 8000):
        # artifacts_dir is the run-specific directory (e.g., artifacts/<repo>-<ts>)
        self.artifacts_dir = artifacts_dir
        self.stdout_limit = stdout_limit
        self.stderr_limit = stderr_limit
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def _write_stream(self, content: str, path: Path, limit: int) -> tuple[str, bool]:
        path.write_text(content)
        truncated = len(content.encode("utf-8")) > limit
        preview = content
        if truncated:
            preview = content.encode("utf-8")[:limit].decode("utf-8", errors="ignore")
        return preview, truncated

    def save(self, report: RunReport, events_path: Optional[Path] = None, name: str = "run_report.json") -> Path:
        data = report.model_dump()
        run_dir = self.artifacts_dir
        if events_path is None:
            events_path = run_dir / "events.log"
        artifacts = {"events_log": str(events_path)}
        data["artifacts"] = artifacts

        for si, stage in enumerate(data.get("stages", [])):
            cmds = stage.get("commands") or []
            stage_dir = run_dir / f"stage_{stage.get('name','unknown')}_{si}"
            stage_dir.mkdir(parents=True, exist_ok=True)
            for ci, cmd in enumerate(cmds):
                stdout_file = stage_dir / f"cmd{ci}_stdout.txt"
                stderr_file = stage_dir / f"cmd{ci}_stderr.txt"
                preview_out, out_trunc = self._write_stream(cmd.get("stdout", "") or "", stdout_file, self.stdout_limit)
                preview_err, err_trunc = self._write_stream(cmd.get("stderr", "") or "", stderr_file, self.stderr_limit)
                cmd["stdout"] = preview_out
                cmd["stderr"] = preview_err
                cmd["stdout_truncated"] = out_trunc
                cmd["stderr_truncated"] = err_trunc
                cmd["stdout_path"] = str(stdout_file)
                cmd["stderr_path"] = str(stderr_file)

        out_path = self.artifacts_dir / name

        def default(o):
            from datetime import datetime

            if isinstance(o, datetime):
                return o.isoformat()
            return str(o)

        out_path.write_text(json.dumps(data, indent=2, default=default))
        return out_path
