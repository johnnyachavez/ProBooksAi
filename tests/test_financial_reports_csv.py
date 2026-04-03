"""Financial report CSV export."""

from __future__ import annotations

import csv

from probooksai.financial_reports import write_report_csv


def test_write_report_csv_with_preamble(tmp_path):
    p = tmp_path / "r.csv"
    n = write_report_csv(
        str(p),
        ["A", "B"],
        [[1, 2], [3, 4]],
        preamble=["Title line", "Subtitle"],
    )
    assert n == 2
    with p.open(encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["Title line"]
    assert rows[1] == ["Subtitle"]
    assert rows[2] == []
    assert rows[3] == ["A", "B"]
    assert rows[4] == ["1", "2"]


def test_write_report_csv_no_preamble(tmp_path):
    p = tmp_path / "x.csv"
    n = write_report_csv(str(p), ["x"], [[9]])
    assert n == 1
    text = p.read_text(encoding="utf-8")
    assert "9" in text
