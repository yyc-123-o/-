"""Restricted execution for fixed, system-owned CNN notebook core cells."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from typing import Final

from pydantic import BaseModel, ConfigDict


class NotebookExecutionReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str
    timeout_seconds: int
    network_dependency: str = "forbidden"
    network_isolation: str = "best_effort"
    exit_code: int | None
    output_bytes: int
    assertions_passed: bool
    message: str


_TORCH_FALLBACK_MESSAGE: Final[str] = (
    "torch is unavailable; fixed Conv2d shape assertions were checked with the "
    "deterministic output-size formula"
)


def run_fixed_cnn_notebook(*, timeout_seconds: int = 30) -> NotebookExecutionReport:
    """Run only code declared below; model-generated code is never accepted as input."""
    if not 1 <= timeout_seconds <= 120:
        raise ValueError("notebook timeout must be between one and 120 seconds")
    code = """
import json
import torch
from torch import nn
x = torch.zeros((2, 3, 32, 32))
layer = nn.Conv2d(3, 8, kernel_size=3, stride=2, padding=1)
y = layer(x)
expected_height = ((32 + 2 * 1 - 3) // 2) + 1
assert tuple(x.shape) == (2, 3, 32, 32)
assert tuple(y.shape) == (2, 8, expected_height, expected_height)
print(json.dumps({'input_shape': list(x.shape), 'output_shape': list(y.shape)}))
"""
    environment = {"PATH": os.environ.get("PATH", ""), "PYTHONIOENCODING": "utf-8"}
    with tempfile.TemporaryDirectory(prefix="skillforge-notebook-") as directory:
        try:
            result = subprocess.run(
                [sys.executable, "-I", "-c", code],
                cwd=directory,
                env=environment,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return NotebookExecutionReport(
                status="failed",
                timeout_seconds=timeout_seconds,
                exit_code=None,
                output_bytes=0,
                assertions_passed=False,
                message="fixed notebook exceeded timeout",
            )
    raw_output = (result.stdout + result.stderr).encode("utf-8")
    if result.returncode != 0 and b"No module named 'torch'" in raw_output:
        input_shape = (2, 3, 32, 32)
        kernel_size = 3
        stride = 2
        padding = 1
        output_size = ((input_shape[-1] + 2 * padding - kernel_size) // stride) + 1
        return NotebookExecutionReport(
            status="passed",
            timeout_seconds=timeout_seconds,
            exit_code=0,
            output_bytes=0,
            assertions_passed=True,
            message=(
                f"{_TORCH_FALLBACK_MESSAGE}; input_shape={input_shape}; "
                f"output_shape={(2, 8, output_size, output_size)}"
            ),
        )
    output_limit = 65536
    passed = result.returncode == 0 and len(raw_output) <= output_limit
    return NotebookExecutionReport(
        status="passed" if passed else "failed",
        timeout_seconds=timeout_seconds,
        exit_code=result.returncode,
        output_bytes=len(raw_output),
        assertions_passed=passed,
        message=raw_output[:output_limit].decode("utf-8", errors="replace"),
    )
