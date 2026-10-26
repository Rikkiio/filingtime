"""Parser governance and source identity tests."""

from pathlib import Path

import pytest

from filingtime.xbrl import parse_filing


def test_library_parser_cannot_open_holdout_before_freeze(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("filingtime.freeze.check_freeze", lambda root: {"status": "missing"})
    with pytest.raises(ValueError, match="unchanged frozen rules"):
        parse_filing(tmp_path, {"split": "holdout"}, tmp_path / "work")
