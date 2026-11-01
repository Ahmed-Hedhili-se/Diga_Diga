"""scripts/discovery_summary.py: the pitch may only quote what the call log supports. Fixture files only."""
import importlib.util

from app.config import ROOT

_spec = importlib.util.spec_from_file_location("discovery_summary", ROOT / "scripts" / "discovery_summary.py")
ds = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ds)

HEADER = "date,company,size_staff,person_role,hires_per_year,cvs_per_role,minutes_per_cv,days_seat_empty,best_quote,would_pilot,price_reaction,referral\n"


def log(tmp_path, *rows):
    p = tmp_path / "call_log.csv"
    p.write_text(HEADER + "".join(r + "\n" for r in rows), encoding="utf-8")
    return p


def lines(tmp_path, *rows):
    return ds.report(ds.summarise(ds.read(log(tmp_path, *rows))))


def test_the_shipped_call_log_has_the_agreed_columns():
    first = (ROOT / "docs" / "discovery" / "call_log.csv").read_text(encoding="utf-8").splitlines()[0]
    assert first == HEADER.strip()


def test_no_rows_means_no_claim(tmp_path):
    assert lines(tmp_path) == ["n calls: 0", "n = 0: no claim possible"]


def test_a_blank_row_is_not_a_call(tmp_path):
    assert lines(tmp_path, ",,,,,,,,,,,")[-1] == "n = 0: no claim possible"


def test_counts_medians_and_pilot_requests(tmp_path):
    out = lines(tmp_path,
                "2026-11-03,A,80,HR,6,120,5,40,\"On lit tout a la main\",yes,ok,B",
                "2026-11-04,B,60,CTO,4,200,3,50,,no,too much,",
                "2026-11-05,C,150,HR,10,,10,30,\"Le plus long, c'est l'arabe\",maybe,,")
    text = "\n".join(out)
    assert "n calls: 3" in text
    assert "We spoke to n=3 people; 1 asked for a pilot." in text
    assert "median minutes to read a CV: 5  (n = 3 answered)" in text
    assert "median CVs per role: 160  (n = 2 answered)" in text      # the blank is ignored, and n says so
    assert "[A] On lit tout a la main" in text and "[C] Le plus long, c'est l'arabe" in text


def test_fewer_than_three_calls_asks_for_quotes_not_percentages(tmp_path):
    out = "\n".join(lines(tmp_path, "2026-11-03,A,80,HR,6,120,5,40,quote,yes,,"))
    assert "fewer than 3 calls" in out and "%" not in out


def test_text_in_a_number_column_is_ignored_not_guessed(tmp_path):
    out = "\n".join(lines(tmp_path, "2026-11-03,A,about 80,HR,6,120,5,40,,yes,,"))
    assert "median staff" not in out and "median hires per year: 6" in out


def test_would_pilot_is_case_insensitive_and_only_yes_counts(tmp_path):
    out = "\n".join(lines(tmp_path, "d,A,1,r,1,1,1,1,,YES,,", "d,B,1,r,1,1,1,1,,Maybe,,", "d,C,1,r,1,1,1,1,,,,"))
    assert "would_pilot=yes: 1  (maybe: 1, no: 0)" in out


def test_main_exits_zero_on_the_shipped_log_and_nonzero_when_missing(tmp_path, capsys):
    assert ds.main([]) == 0
    assert ds.main(["--file", str(tmp_path / "missing.csv")]) == 1
