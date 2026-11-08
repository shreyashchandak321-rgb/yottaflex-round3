"""Tests for the generator and validator.

Run:  python -m pytest tests/ -q
The heavy checks (full-dataset validation) live in src/validate.py; these
tests pin the generator's contract on the fast 'starter' scale.
"""

import csv
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import generate as gen  # noqa: E402


def read(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_starter_generation(tmp_path):
    out = tmp_path / "starter"
    manifest = gen.generate("starter", str(out))
    assert manifest["counts"]["reviews"] >= 300
    assert manifest["feedback_total"] >= 500
    assert manifest["counts"]["support_messages"] >= 200
    # every anomaly type is present and labelled
    issues = {r["issue_type"] for r in read(out / "ground_truth.csv")}
    assert issues == {"label_contradicts_text", "duplicate_response",
                      "customer_identity_leaked", "theme_outside_taxonomy",
                      "test_label_in_input"}


def test_reproducibility_same_seed(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    gen.generate("starter", str(a))
    gen.generate("starter", str(b))
    for name in ["reviews.csv", "survey_responses.csv", "support_messages.csv",
                 "ground_truth.csv"]:
        ha = hashlib.sha256((a / name).read_bytes()).hexdigest()
        hb = hashlib.sha256((b / name).read_bytes()).hexdigest()
        assert ha == hb, f"{name} differs between runs with the same seed"


def test_id_formats_and_fk(tmp_path):
    out = tmp_path / "starter"
    gen.generate("starter", str(out))
    customers = {r["customer_id"] for r in read(out / "customers.csv")}
    themes = {r["theme_id"] for r in read(out / "themes.csv")}
    reviews = read(out / "reviews.csv")
    assert all(r["review_id"].startswith("REV-2026-") for r in reviews)
    assert all(r["customer_id"] in customers for r in reviews)
    # theme FK may only dangle for labelled ground-truth anomalies
    gt = {r["record_id"] for r in read(out / "ground_truth.csv")
          if r["issue_type"] == "theme_outside_taxonomy"}
    dangling = {r["review_id"] for r in reviews if r["theme_id"] not in themes}
    assert dangling <= gt


def test_ground_truth_not_in_inputs(tmp_path):
    out = tmp_path / "starter"
    gen.generate("starter", str(out))
    for name in ["reviews.csv", "survey_responses.csv", "support_messages.csv"]:
        header = open(out / name, encoding="utf-8").readline()
        assert "issue_type" not in header


def test_label_balance_is_broad(tmp_path):
    out = tmp_path / "starter"
    gen.generate("starter", str(out))
    from collections import Counter
    counts = Counter()
    for name in ["reviews.csv", "survey_responses.csv"]:
        for r in read(out / name):
            counts[r["sentiment_label_id"]] += 1
    total = sum(counts.values())
    for label, n in counts.items():
        assert n / total < 0.55, f"{label} dominates at {n / total:.0%}"


def test_validator_passes_on_starter(tmp_path):
    out = tmp_path / "starter"
    gen.generate("starter", str(out))
    result = subprocess.run(
        [sys.executable, str(ROOT / "src" / "validate.py"), "--data", str(out)],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
