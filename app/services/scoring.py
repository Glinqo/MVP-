import sys

from .data_loader import ROOT


XINGCHEN_DIR = ROOT / "xingchen"
if str(XINGCHEN_DIR) not in sys.path:
    sys.path.insert(0, str(XINGCHEN_DIR))

from code_module_scoring import score_diagnostic  # noqa: E402


def score_answers(payload):
    return score_diagnostic(payload or {"answers": {}})
