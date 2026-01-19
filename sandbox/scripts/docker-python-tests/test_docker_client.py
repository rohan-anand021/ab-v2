from __future__ import annotations

import sys
import tempfile
import uuid
from pathlib import Path
import yaml

import sys

sys.path.append(str(Path(__file__).resolve().parents[3]))

from sandbox.docker_client import DockerClient


def load_instance(path: Path) -> dict:
    data = yaml.safe_load(path.read_text())
    instances = data.get("instances") or []
    if not instances:
        raise SystemExit("No instances in config")
    return instances[0]


def run_instance(instance: dict, image: str = "runner-core") -> int:
    client = DockerClient()
    container = f"docker-client-test-{uuid.uuid4().hex[:8]}"
    results: list[tuple[str, object]] = []

    res = client.run_container(image=image, name=container)
    results.append(("start", res))
    if res.exit_code not in (0, None):
        print("Failed to start container")
        client.rm(container)
        return 1

    res = client.exec(container, ["bash", "-lc", f"cd /workspace && git clone {instance['repo_url']} repo"])
    results.append(("clone", res))
    if res.exit_code != 0:
        print("Clone failed")
        client.stop(container)
        client.rm(container)
        return 1

    res = client.exec(container, ["bash", "-lc", f"cd /workspace/repo && git checkout {instance['commit']}"])
    results.append(("checkout", res))
    if res.exit_code != 0:
        print("Checkout failed")
        client.stop(container)
        client.rm(container)
        return 1

    test_patch = instance.get("test_patch") or ""
    if test_patch.strip():
        tmp_dir = Path(tempfile.mkdtemp(prefix="docker_client_patch_"))
        host_patch = tmp_dir / "patch.diff"
        host_patch.write_text(test_patch)
        res = client.cp(str(host_patch), f"{container}:/tmp/test_patch.diff")
        results.append(("write_patch", res))
        if res.exit_code != 0:
            print("Patch write failed")
            print(res.stdout)
            print(res.stderr)
            client.stop(container)
            client.rm(container)
            return 1
        res = client.exec(container, ["bash", "-lc", "cd /workspace/repo && patch -p1 < /tmp/test_patch.diff"])
        results.append(("apply_patch", res))
        if res.exit_code != 0:
            print("Patch apply failed")
            print(res.stdout)
            print(res.stderr)
            client.stop(container)
            client.rm(container)
            return 1

    res = client.exec(
        container,
        [
            "bash",
            "-lc",
            "cd /workspace/repo && python - <<'PY'\nfrom pathlib import Path\nrepl = {\n    'from collections import MutableMapping': 'from collections.abc import MutableMapping',\n    'from collections import Mapping': 'from collections.abc import Mapping',\n    'collections.MutableMapping': 'collections.abc.MutableMapping',\n    'collections.Mapping': 'collections.abc.Mapping',\n}\nfor p in Path('.').rglob('*.py'):\n    txt = p.read_text()\n    new = txt\n    for old, new_val in repl.items():\n        new = new.replace(old, new_val)\n    if new != txt:\n        p.write_text(new)\nPY",
        ],
    )
    results.append(("compat_rewrite", res))
    if res.exit_code != 0:
        print("Compat rewrite failed")
        client.stop(container)
        client.rm(container)
        return 1

    for cmd in instance.get("setup_commands", []):
        res = client.exec(container, ["bash", "-lc", f"cd /workspace/repo && {cmd}"])
        results.append(("setup", res))
        if res.exit_code != 0 or res.timed_out:
            print("Setup failed")
            client.stop(container)
            client.rm(container)
            return 1

    res = client.exec(container, ["bash", "-lc", f"cd /workspace/repo && {instance['test_command']}"])
    results.append(("test", res))

    client.stop(container)
    client.rm(container)

    for stage, r in results:
        print(f"[{stage}] exit={r.exit_code} timeout={r.timed_out}")

    expected_fail = instance.get("expected_fail", True)
    if expected_fail:
        return 0 if res.exit_code != 0 else 1
    return res.exit_code or 0


def main() -> None:
    cfg_path = Path("scripts/swe-bench/swebench_smoke_requests.yaml")
    instance = load_instance(cfg_path)
    code = run_instance(instance)
    sys.exit(code)


if __name__ == "__main__":
    main()
