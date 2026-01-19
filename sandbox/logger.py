from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


class EventLogger:
    def __init__(self, path: Path, name: str = "sandbox", echo: bool = True) -> None:
        self.path = path
        self.name = name
        self.echo = echo
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(
        self,
        level: str,
        message: str,
        stage: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        payload = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "logger": self.name,
            "level": level.lower(),
            "stage": stage,
            "message": message,
            "context": context or {},
            "data": data or {},
        }
        line = json.dumps(payload, ensure_ascii=True)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        if self.echo:
            print(line)

    def info(self, message: str, stage: Optional[str] = None, context: Optional[Dict[str, Any]] = None, data: Optional[Dict[str, Any]] = None) -> None:
        self.emit("info", message, stage=stage, context=context, data=data)

    def warning(self, message: str, stage: Optional[str] = None, context: Optional[Dict[str, Any]] = None, data: Optional[Dict[str, Any]] = None) -> None:
        self.emit("warning", message, stage=stage, context=context, data=data)

    def error(self, message: str, stage: Optional[str] = None, context: Optional[Dict[str, Any]] = None, data: Optional[Dict[str, Any]] = None) -> None:
        self.emit("error", message, stage=stage, context=context, data=data)
