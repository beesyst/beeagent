from __future__ import annotations

import subprocess

from beeagent_module.core.accelerator import detect_accelerator


def _result(output: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout=output, stderr="")


def test_detects_cpu_without_usable_nvidia(monkeypatch) -> None:
    monkeypatch.setattr(
        "beeagent_module.core.accelerator.subprocess.run",
        lambda *args, **kwargs: _result("", returncode=1),
    )
    assert detect_accelerator() == "cpu"


def test_detects_cuda_for_supported_nvidia(monkeypatch) -> None:
    monkeypatch.setattr(
        "beeagent_module.core.accelerator.subprocess.run",
        lambda *args, **kwargs: _result("560.42.01\n"),
    )
    assert detect_accelerator() == "cuda"


def test_detector_has_no_extractor_profile_semantics() -> None:
    source = __import__("inspect").getsource(
        __import__("beeagent_module.core.accelerator", fromlist=["*"])
    )
    assert "docling-" not in source
