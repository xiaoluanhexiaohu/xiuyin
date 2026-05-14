import pytest

pytest.importorskip("numpy")

from core.aligner import AlignmentResult
from core.correction_planner import CorrectionPlan
from core.mixer import MixResult
from core.renderer import RenderResult
from core.report import build_report, write_report


def test_report_write(tmp_path):
    plan = CorrectionPlan([0.0], [220.0], [230.0], [225.0], [39.0], 0.5, 0.6, 300, [], [], {})
    report = build_report(
        {"id": "x"},
        {"reference": "test", "user": "test"},
        AlignmentResult([], [0], 0.8, [], 1.0, []),
        plan,
        RenderResult("corrected.wav", "placeholder", False, None, []),
        MixResult("mix.wav", "vocal_only", 0.5, 1.0, []),
        {"total": 0.1},
        [],
    )
    path = write_report(report, tmp_path / "report.json")
    assert path.exists()
    assert report["render"]["renderer"] == "placeholder"
