"""Where a copy of the app finds its models, and that it never goes looking online."""

from __future__ import annotations

import sys

import pytest

from luikki import models


def test_an_installed_app_reads_its_own_bundle(monkeypatch, tmp_path):
    monkeypatch.delenv("LUIKKI_MODELS", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / models.MANGA_LINE).write_bytes(b"onnx")

    assert models.model_file(models.MANGA_LINE) == tmp_path / "models" / models.MANGA_LINE


def test_a_missing_model_says_how_to_get_it_and_fetches_nothing(monkeypatch, tmp_path):
    monkeypatch.setenv("LUIKKI_MODELS", str(tmp_path))
    fetched = []
    monkeypatch.setattr(models.urllib.request, "urlretrieve", lambda *args: fetched.append(args))

    with pytest.raises(FileNotFoundError, match="luikki models"):
        models.model_file(models.BUBBLE_DETECTOR)
    assert fetched == []
