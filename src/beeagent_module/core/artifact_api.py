from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from beeagent_module.core.runtime_context import RuntimeContext


# Сохранение и чтение артефактов модулей в контролируемой структуре директорий, связанной с run_id и module_id
class ArtifactAPI:
    def __init__(
        self,
        context: RuntimeContext,
        storage_dir: Path,
        logger: logging.Logger,
    ) -> None:

        if not isinstance(context, RuntimeContext):
            raise ValueError("context must be a RuntimeContext instance")
        if not isinstance(storage_dir, Path):
            raise ValueError("storage_dir must be a Path instance")

        self._context = context
        self._storage_dir = storage_dir
        self._logger = logger

        self._artifact_dir = self._build_artifact_dir()
        self._artifact_dir.mkdir(parents=True, exist_ok=True)

    def _build_artifact_dir(self) -> Path:
        runs_dir = self._storage_dir / "runs"
        run_dir = runs_dir / self._context.run_id
        module_dir = run_dir / f"module-{self._context.module_id}"
        return module_dir

    def artifact_dir(self) -> Path:
        return self._artifact_dir

    def write_json(
        self,
        filename: str,
        data: dict[str, Any] | list[Any],
    ) -> Path:
        self._validate_filename(filename)
        artifact_path = self._artifact_dir / filename

        try:
            artifact_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self._logger.info(
                "artifact written: module_id=%s run_id=%s file=%s path=%s",
                self._context.module_id,
                self._context.run_id,
                filename,
                artifact_path.relative_to(self._storage_dir),
            )
            return artifact_path
        except OSError as e:
            self._logger.exception(
                "failed to write artifact: module_id=%s file=%s error=%s",
                self._context.module_id,
                filename,
                e,
            )
            raise

    def write_text(self, filename: str, content: str) -> Path:
        self._validate_filename(filename)
        artifact_path = self._artifact_dir / filename

        try:
            artifact_path.write_text(content, encoding="utf-8")
            self._logger.info(
                "artifact written: module_id=%s run_id=%s file=%s path=%s",
                self._context.module_id,
                self._context.run_id,
                filename,
                artifact_path.relative_to(self._storage_dir),
            )
            return artifact_path
        except OSError as e:
            self._logger.exception(
                "failed to write artifact: module_id=%s file=%s error=%s",
                self._context.module_id,
                filename,
                e,
            )
            raise

    def read_json(self, filename: str) -> dict[str, Any] | list[Any]:
        self._validate_filename(filename)
        artifact_path = self._artifact_dir / filename

        if not artifact_path.exists():
            raise ValueError(f"Artifact not found: {filename}")

        try:
            content = artifact_path.read_text(encoding="utf-8")
            return json.loads(content)
        except (OSError, json.JSONDecodeError) as e:
            self._logger.exception(
                "failed to read artifact: module_id=%s file=%s error=%s",
                self._context.module_id,
                filename,
                e,
            )
            raise

    def read_text(self, filename: str) -> str:
        self._validate_filename(filename)
        artifact_path = self._artifact_dir / filename

        if not artifact_path.exists():
            raise ValueError(f"Artifact not found: {filename}")

        try:
            return artifact_path.read_text(encoding="utf-8")
        except OSError as e:
            self._logger.exception(
                "failed to read artifact: module_id=%s file=%s error=%s",
                self._context.module_id,
                filename,
                e,
            )
            raise

    def list_artifacts(self) -> list[Path]:
        if not self._artifact_dir.exists():
            return []
        return sorted(self._artifact_dir.glob("*"))

    def _validate_filename(self, filename: str) -> None:
        if not filename or "/" in filename or "\\" in filename:
            raise ValueError(
                f"Invalid filename: must be a simple name without path separators. Got: {filename}"
            )
