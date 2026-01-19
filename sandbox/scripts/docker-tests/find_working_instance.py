from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable, Optional

CONFIG_PATH = Path("scripts/swe-bench/tmp_instance.yaml")
RUNNER = Path("sandbox/scripts/docker-tests/runner_core_swebench_smoke.sh")
ENV_ROOT = Path("SWE-bench/swebench/resources/swebench-og")


def iter_instances(limit: Optional[int] = None, allow: Optional[list[str]] = None, block: Optional[list[str]] = None) -> Iterable[dict]:
    try:
        from datasets import load_dataset
    except ImportError:
        sys.exit("Install `datasets` to load SWE-bench (e.g., `uv add datasets`).")

    cache_dir = Path(".hf_cache").resolve()
    cache_dir.mkdir(exist_ok=True)
    stream = load_dataset(
        "princeton-nlp/SWE-bench_Lite",
        split="test",
        streaming=True,
        cache_dir=str(cache_dir),
    )
    count = 0
    for row in stream:
        repo = row.get("repo", "")
        repo_norm = repo.replace("/", "__")
        def match(item: str) -> bool:
            item = item.strip()
            if not item:
                return False
            return item in repo or item in repo_norm
        if allow and not any(match(a) for a in allow):
            print(f"Skipping {row.get('instance_id')} (allowlist mismatch)", flush=True)
            continue
        if block and any(match(b) for b in block):
            print(f"Skipping {row.get('instance_id')} (blocklist)", flush=True)
            continue
        yield row
        count += 1
        if limit and limit > 0 and count >= limit:
            break


def env_for_instance(instance: dict) -> Optional[Path]:
    repo = (instance.get("repo") or "").replace("/", "__")
    issue = (instance.get("instance_id") or "").split("-")[-1]
    path = ENV_ROOT / repo / issue / "environment.yml"
    return path if path.is_file() else None


def parse_pip_deps(env_path: Path) -> list[str]:
    deps: list[str] = []
    in_pip = False
    base_indent = 0
    for line in env_path.read_text().splitlines():
        if not in_pip:
            if line.strip().startswith("pip:"):
                in_pip = True
                base_indent = len(line) - len(line.lstrip())
            continue
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= base_indent:
            break
        stripped = line.strip()
        if stripped.startswith("-"):
            pkg = stripped[1:].strip()
            if pkg:
                deps.append(pkg)
    return deps


def adjust_deps_for_compat(repo: str, deps: list[str]) -> list[str]:
    repo_lower = repo.lower()
    patched: list[str] = []
    for d in deps:
        if "setuptools" in d and ("astropy" in repo_lower or "numpy" in repo_lower):
            patched.append("setuptools<58")
            continue
        if "requests" in repo_lower and d.strip().startswith("pytest"):
            continue
        patched.append(d)
    if "requests" in repo_lower:
        patched.append("pytest==6.0.0")
        patched.append("py>=1.8.2")
    return patched


def build_config(instance: dict) -> dict:
    def _normalize_list(val):
        if val is None:
            return []
        if isinstance(val, str):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, list):
                    return [str(x).strip() for x in parsed if x]
                return [str(parsed).strip()]
            except Exception:
                return [val.strip()]
        if isinstance(val, (list, tuple)):
            return [str(x).strip() for x in val if x]
        return [str(val).strip()]

    fail = _normalize_list(instance.get("FAIL_TO_PASS"))
    pass_list = _normalize_list(instance.get("PASS_TO_PASS"))

    tests = " ".join(fail) if fail else ""
    test_cmd = (
        f"PYTHONWARNINGS=ignore::UserWarning python -m pytest -q {tests}"
        if tests
        else "PYTHONWARNINGS=ignore::UserWarning python -m pytest -q"
    )

    setup_cmds = ["python -m pip install -U pip setuptools wheel"]

    env_path = env_for_instance(instance)
    use_requirements = True
    if "requests" in (instance.get("repo") or "").lower():
        use_requirements = False
    if env_path:
        deps = adjust_deps_for_compat(instance.get("repo", ""), parse_pip_deps(env_path))
        if deps:
            setup_cmds.append("python -m pip install " + " ".join(deps))

    repo_lower = (instance.get("repo") or "").lower()

    if "pytest-dev/pytest" not in repo_lower:
        setup_cmds.append("pip install pytest")
        if use_requirements:
            setup_cmds.extend(
                [
                    "pip install -r requirements.txt || true",
                    "pip install -r requirements-dev.txt || true",
                ]
            )
    setup_cmds.append("pip install -e .")

    return {
        "instances": [
            {
                "id": instance["instance_id"],
                "repo_url": f"https://github.com/{instance['repo']}",
        "commit": instance["base_commit"],
        "environment_setup_commit": instance.get("environment_setup_commit")
        or instance["base_commit"],
        "version": str(instance.get("version") or ""),
        "test_command": test_cmd,
        "test_patch": instance.get("test_patch") or "",
        "setup_commands": setup_cmds,
        "FAIL_TO_PASS": fail,
        "PASS_TO_PASS": pass_list,
        "expected_fail": True,
        "notes": "Auto-generated from SWE-bench Lite",
            }
        ]
    }


def write_config(cfg: dict) -> Path:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(cfg, indent=2)
    CONFIG_PATH.write_text(text)
    return CONFIG_PATH


def run_instance(cfg_path: Path) -> int:
    env = os.environ.copy()
    env["CONFIG"] = str(cfg_path)
    proc = subprocess.run(
        ["bash", str(RUNNER)],
        stdout=sys.stdout,
        stderr=sys.stderr,
        env=env,
    )
    return proc.returncode


def main() -> None:
    limit_env = os.environ.get("SWEBENCH_SCAN_LIMIT")
    limit = int(limit_env) if limit_env else None
    allow = os.environ.get("SWEBENCH_ALLOW")
    block = os.environ.get("SWEBENCH_BLOCK") or ""
    allow_list = [a.strip() for a in allow.split(",") if a.strip()] if allow else []
    block_list = [b.strip() for b in block.split(",") if b.strip()] if block else []

    for inst in iter_instances(limit=limit, allow=allow_list, block=block_list):
        env_path = env_for_instance(inst)
        if env_path:
            inst["_env_path"] = str(env_path)
        cfg = build_config(inst)
        cfg_path = write_config(cfg)
        print(f"Trying {inst['instance_id']}...", flush=True)
        code = run_instance(cfg_path)
        if code == 0:
            print(f"Success on {inst['instance_id']}")
            return
        else:
            print(f"Failed on {inst['instance_id']} (exit {code}), continuing...")
    sys.exit("No instance succeeded within scan limit")


if __name__ == "__main__":
    main()
