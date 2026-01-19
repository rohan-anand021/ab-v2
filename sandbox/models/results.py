from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class StageStatus(str, Enum):
    success = "success"
    failed = "failed"
    skipped = "skipped"


class CommandResult(BaseModel):
    command: str = Field(description="Command string executed.")
    cwd: Optional[str] = Field(default=None, description="Working directory used.")
    env: dict = Field(default_factory=dict, description="Env vars applied to the command.")
    exit_code: Optional[int] = Field(default=None, description="Exit code (None if timeout).")
    stdout: str = Field(default="", description="Captured stdout.")
    stderr: str = Field(default="", description="Captured stderr.")
    duration_sec: float = Field(default=0.0, description="Duration in seconds.")
    started_at: datetime = Field(default_factory=datetime.utcnow, description="Start timestamp.")
    timed_out: bool = Field(default=False, description="True if command timed out.")


class StageResult(BaseModel):
    name: str = Field(description="Stage name (clone, checkout, setup, test, etc.).")
    status: StageStatus = Field(default=StageStatus.success, description="Stage status.")
    commands: List[CommandResult] = Field(default_factory=list, description="Commands run.")
    error: Optional[str] = Field(default=None, description="Error summary, if any.")


class RunReport(BaseModel):
    sandbox: dict = Field(default_factory=dict, description="SandboxConfig as dict.")
    repo: dict = Field(default_factory=dict, description="RepoSpec as dict.")
    task: dict = Field(default_factory=dict, description="TaskSpec as dict.")
    stages: List[StageResult] = Field(default_factory=list, description="Ordered stage results.")
    started_at: datetime = Field(default_factory=datetime.utcnow, description="Run start time.")
    completed_at: Optional[datetime] = Field(default=None, description="Run end time.")
    success: bool = Field(default=False, description="True if all expected conditions met.")
    notes: Optional[str] = Field(default=None, description="Optional run notes.")
