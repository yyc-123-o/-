from __future__ import annotations

import pytest

from skillforge_kb.resources.notebook_runner import run_fixed_cnn_notebook


def test_notebook_timeout_is_bounded() -> None:
    with pytest.raises(ValueError, match="between one and 120"):
        run_fixed_cnn_notebook(timeout_seconds=121)


def test_notebook_reports_fixed_execution_contract() -> None:
    report = run_fixed_cnn_notebook(timeout_seconds=30)
    assert report.network_dependency == "forbidden"
    assert report.network_isolation == "best_effort"
    assert report.timeout_seconds == 30
    assert report.status in {"passed", "failed"}
