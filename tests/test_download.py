"""Downloader: skips files already present, retries, never leaves a half-written file in place."""
import json

import pytest

from recruit import download


class FakeHost:
    """Serves bytes from a dict; fails the first `fail_times` requests for each URL."""

    def __init__(self, files, fail_times=0):
        self.files = files
        self.fail_times = fail_times
        self.calls = []

    def __call__(self, url, timeout):
        self.calls.append(url)
        if self.calls.count(url) <= self.fail_times:
            raise OSError("connection reset")
        return self.files[url]


def test_fetch_writes_file_and_skips_when_present(tmp_path):
    host = FakeHost({"u/a.json": b"[1]"})
    dest = tmp_path / "a.json"
    assert download.fetch_to_file("u/a.json", dest, fetch=host, sleep=lambda s: None) is True
    assert dest.read_bytes() == b"[1]"
    assert download.fetch_to_file("u/a.json", dest, fetch=host, sleep=lambda s: None) is False
    assert host.calls == ["u/a.json"]


def test_fetch_retries_with_backoff_then_succeeds(tmp_path):
    host = FakeHost({"u/a.json": b"[]"}, fail_times=2)
    waits = []
    download.fetch_to_file("u/a.json", tmp_path / "a.json", fetch=host, retries=3,
                           backoff=1.5, sleep=waits.append)
    assert waits == [1.5, 3.0]
    assert (tmp_path / "a.json").read_bytes() == b"[]"


def test_fetch_gives_up_and_leaves_no_file(tmp_path):
    host = FakeHost({"u/a.json": b"[]"}, fail_times=10)
    with pytest.raises(OSError):
        download.fetch_to_file("u/a.json", tmp_path / "a.json", fetch=host, retries=2,
                               backoff=0, sleep=lambda s: None)
    assert list(tmp_path.iterdir()) == []


def test_statsbomb_downloads_competitions_matches_events_lineups(tmp_path):
    base = "https://x/data"
    matches = [{"match_id": 11}, {"match_id": 12}]
    files = {
        f"{base}/competitions.json": b"[]",
        f"{base}/matches/2/27.json": json.dumps(matches).encode(),
    }
    for mid in (11, 12):
        files[f"{base}/events/{mid}.json"] = b"[]"
        files[f"{base}/lineups/{mid}.json"] = b"[]"
    host = FakeHost(files)
    summary = download.download_statsbomb(base, tmp_path, season_id=27, competition_ids=[2],
                                          fetch=host, delay=0, sleep=lambda s: None)
    assert sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*.json")) == [
        "competitions.json", "events/11.json", "events/12.json",
        "lineups/11.json", "lineups/12.json", "matches/2/27.json",
    ]
    assert summary == {"downloaded": 6, "skipped": 0, "matches": 2}
    # second run is resumable: nothing fetched again
    host.calls.clear()
    again = download.download_statsbomb(base, tmp_path, season_id=27, competition_ids=[2],
                                        fetch=host, delay=0, sleep=lambda s: None)
    assert host.calls == [] and again["skipped"] == 6
