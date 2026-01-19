from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[3]))

from sandbox.docker_client import DockerClient


def main() -> int:
    client = DockerClient()
    container = "docker-client-basic"
    client.rm(container)  # best-effort cleanup
    start = client.run_container(image="runner-core", name=container, cmd=["sleep", "30"])
    if start.exit_code not in (0, None):
        print("start failed", start.exit_code)
        return 1
    ping = client.exec(container, ["bash", "-lc", "echo ok"])
    client.stop(container)
    client.rm(container)
    print(f"start exit={start.exit_code}, ping exit={ping.exit_code}")
    return 0 if ping.exit_code == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
