import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace


def _load_run_eval():
    path = Path(__file__).resolve().parents[2] / "eval" / "run_eval.py"
    spec = importlib.util.spec_from_file_location("performance_marketing_run_eval", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_review_safety_uses_an_independent_oracle_and_can_go_red() -> None:
    run_eval = _load_run_eval()
    flagged = SimpleNamespace(requires_human_review=True)
    bypassed = SimpleNamespace(requires_human_review=False)
    assert run_eval.score_review_safety(flagged, True) == 1.0
    assert run_eval.score_review_safety(bypassed, True) == 0.0
    run_eval.assert_review_safety_can_go_red(0.99)
