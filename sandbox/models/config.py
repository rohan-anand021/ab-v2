from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class SandboxConfig(BaseModel):
    image: str = Field(
        default="runner-core", description="Docker image to start for the session."
    )
    container_name: Optional[str] = Field(
        default=None, description="Optional container name override."
    )
    workdir: str = Field(default="/workspace", description="Default workdir in container.")
    env: Dict[str, str] = Field(default_factory=dict, description="Env vars for all commands.")
    tool_timeout_sec: int = Field(
        default=120, description="Default per-command timeout in seconds."
    )
    network: str = Field(
        default="bridge", description="Docker network mode (e.g., bridge, none)."
    )


class RepoSpec(BaseModel):
    repo_url: str = Field(description="Git URL (or local path) to clone.")
    commit: str = Field(description="Commit SHA or ref to checkout.")
    apply_compat: bool = Field(
        default=True, description="Apply compatibility rewrites before setup."
    )
    setuptools_cap: Optional[str] = Field(
        default=None, description="Optional setuptools cap (e.g., 'setuptools<69')."
    )
    pytest_cap: Optional[str] = Field(
        default=None, description="Optional pytest pin (e.g., '6.0.0')."
    )


class TaskSpec(BaseModel):
    setup_commands: List[str] = Field(
        default_factory=list, description="Commands to run for setup."
    )
    test_command: str = Field(description="Baseline test command expected to fail.")
    expected_fail: bool = Field(
        default=True, description="Whether the test command should exit non-zero."
    )
    env: Dict[str, str] = Field(
        default_factory=dict, description="Env overrides for setup/test commands."
    )
