"""Load the standalone 学情诊断 Agent FastAPI app so it can be mounted into the platform.

The diagnosis agent lives in ``学情诊断Agent/`` as a self-contained FastAPI app with
relative imports (``models.*``, ``core.*``, ``generators.*``) rooted at its own directory.
We load it by file path under a dedicated module name to avoid colliding with any other
top-level ``main`` module in the process.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

_DIAGNOSIS_DIR = Path(__file__).resolve().parents[2] / "学情诊断Agent"
_MODULE_NAME = "_skillforge_diagnosis_agent"


def load_diagnosis_app() -> ModuleType:
    main_path = _DIAGNOSIS_DIR / "main.py"
    if not main_path.is_file():
        raise FileNotFoundError(f"diagnosis agent entry not found: {main_path}")

    # The diagnosis app resolves its own models/core/generators relative to its directory.
    if str(_DIAGNOSIS_DIR) not in sys.path:
        sys.path.insert(0, str(_DIAGNOSIS_DIR))

    spec = importlib.util.spec_from_file_location(_MODULE_NAME, main_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load diagnosis agent from {main_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module
