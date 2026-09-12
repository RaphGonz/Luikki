"""The project lives in the user's data folder, and one left in temp comes along."""

from __future__ import annotations

from pathlib import Path

import platformdirs

from luikki.web import project


def _redirect(monkeypatch, tmp_path: Path) -> tuple[Path, Path]:
    data, temp = tmp_path / "data", tmp_path / "temp"
    monkeypatch.setattr(platformdirs, "user_data_dir", lambda *args, **kwargs: str(data / "Luikki"))
    monkeypatch.setattr(project.tempfile, "gettempdir", lambda: str(temp))
    return data / "Luikki", temp / "luikki"


def test_a_project_left_in_temp_is_copied_across_once(monkeypatch, tmp_path):
    workdir, legacy = _redirect(monkeypatch, tmp_path)
    (legacy / "pages" / "0001").mkdir(parents=True)
    (legacy / "project.json").write_text('{"current": 1}')
    (legacy / "pages" / "0001" / "page.json").write_text("{}")

    assert project.default_workdir() == workdir
    assert (workdir / "project.json").read_text() == '{"current": 1}'
    assert (workdir / "pages" / "0001" / "page.json").exists()
    assert not workdir.with_name("Luikki.part").exists()
    assert (legacy / "project.json").exists(), "the old copy is left, never moved"


def test_a_project_already_in_place_is_never_overwritten(monkeypatch, tmp_path):
    workdir, legacy = _redirect(monkeypatch, tmp_path)
    workdir.mkdir(parents=True)
    (workdir / "project.json").write_text('{"current": 2}')
    legacy.mkdir(parents=True)
    (legacy / "project.json").write_text('{"current": 1}')

    assert project.default_workdir() == workdir
    assert (workdir / "project.json").read_text() == '{"current": 2}'
