import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from stats import clopper_pearson, cohen_kappa, kendall_tau, rate  # noqa: E402


def test_clopper_pearson_reference_values():
    lo, hi = clopper_pearson(0, 10)
    assert lo == 0.0 and hi == pytest.approx(0.3085, abs=1e-4)
    lo, hi = clopper_pearson(5, 10)
    assert lo == pytest.approx(0.1871, abs=1e-4) and hi == pytest.approx(0.8129, abs=1e-4)
    assert clopper_pearson(10, 10)[1] == 1.0
    with pytest.raises(ValueError):
        clopper_pearson(3, 2)


def test_rate_text():
    assert rate(0, 40)["text"].startswith("0/40 (0.0%, 95% CI 0.0–")
    assert rate(0, 0)["rate"] is None


def test_kendall_and_kappa():
    assert kendall_tau([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1)
    assert kendall_tau([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1)
    assert cohen_kappa(list("aabb"), list("aabb")) == 1
    assert cohen_kappa(list("abab"), list("aabb")) == pytest.approx(0)
