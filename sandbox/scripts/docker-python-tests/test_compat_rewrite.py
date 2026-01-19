from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[3]))

from sandbox.compat import apply_collections_rewrite
from sandbox.docker_client import DockerClient


def main() -> int:
    client = DockerClient()
    container = "compat-rewrite-test"
    client.rm(container)
    start = client.run_container(image="runner-core", name=container, cmd=["sleep", "60"])
    if start.exit_code not in (0, None):
        print("start failed", start.exit_code)
        return 1
    create = client.exec(
        container,
        [
            "bash",
            "-lc",
            "cd /workspace && mkdir -p repo && echo \"from collections import Mapping\\nprint(Mapping)\" > /workspace/repo/demo.py",
        ],
    )
    if create.exit_code != 0:
        print("create failed", create.exit_code)
        client.stop(container)
        client.rm(container)
        return 1
    exit_code = apply_collections_rewrite(client, container, workdir="/workspace/repo")
    updated = client.exec(container, ["bash", "-lc", "cd /workspace/repo && cat demo.py"])
    client.stop(container)
    client.rm(container)
    print(updated.stdout)
    return 0 if exit_code == 0 and "collections.abc" in updated.stdout else 1


if __name__ == "__main__":
    raise SystemExit(main())
