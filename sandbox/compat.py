from __future__ import annotations

from typing import Optional

from sandbox.docker_client import DockerClient
from sandbox.logger import EventLogger
from sandbox.scripts.snippets import COLLECTIONS_REWRITE


def apply_collections_rewrite(client: DockerClient, container: str, workdir: str = "/workspace/repo", logger: Optional[EventLogger] = None) -> int:
    script = COLLECTIONS_REWRITE.format(workdir=workdir)
    res = client.exec(container, ["bash", "-lc", script])
    if logger:
        logger.info("compat_collections", stage="compat_rewrite", data={"exit": res.exit_code})
    return res.exit_code or 0


def apply_setuptools_cap(client: DockerClient, container: str, version_cap: str = "setuptools<69", workdir: str = "/workspace/repo", logger: Optional[EventLogger] = None) -> int:
    res = client.exec(
        container,
        ["bash", "-lc", f"cd {workdir} && python -m pip install -U pip wheel {version_cap}"],
    )
    if logger:
        logger.info("compat_setuptools_cap", stage="setup", data={"exit": res.exit_code, "cap": version_cap})
    return res.exit_code or 0


def apply_pytest_cap(client: DockerClient, container: str, version: str, workdir: str = "/workspace/repo", logger: Optional[EventLogger] = None) -> int:
    res = client.exec(
        container,
        ["bash", "-lc", f"cd {workdir} && python -m pip install pytest=={version}"],
    )
    if logger:
        logger.info("compat_pytest_cap", stage="setup", data={"exit": res.exit_code, "version": version})
    return res.exit_code or 0
