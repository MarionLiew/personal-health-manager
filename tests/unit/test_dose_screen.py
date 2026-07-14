from pathlib import Path

from health_agent.parsers.dose_screen import dose_screen_warnings, parse_dose_screen_text


def test_dose_screen_candidates_keep_total_separate_from_event_dlp() -> None:
    text = Path("tests/fixtures/fictional_dose_screen.txt").read_text()
    candidates = parse_dose_screen_text(text, "fictional-hash")
    fields = [item["field"] for item in candidates]
    assert fields.count("event_dlp") == 2
    assert fields.count("total_dlp") == 1
    assert fields.count("ctdi_vol") == 2
    assert all(item["region"]["line"] > 0 for item in candidates)
    assert dose_screen_warnings(candidates) == []


def test_dose_screen_warns_when_total_and_event_sum_disagree() -> None:
    candidates = parse_dose_screen_text("DLP: 10\nDLP: 20\nTotal DLP: 100")
    assert dose_screen_warnings(candidates)
