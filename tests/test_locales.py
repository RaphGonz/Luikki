"""Every word the artist reads lives in a locale file, and the locales agree.

A key missing from `en.json` shows on screen as the key itself. A key nothing
uses is a sentence someone will translate for nothing. A key assembled at
runtime is one neither check can see. All three are caught here, not by an
artist reading the page.
"""

from __future__ import annotations

import json
import re
import warnings
from html.parser import HTMLParser
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "src" / "luikki"
STATIC = SOURCE / "web" / "static"
LOCALES = STATIC / "locales"
PLURAL_FORMS = {"zero", "one", "two", "few", "many", "other"}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _english() -> dict:
    return _load(LOCALES / "en.json")


def _script() -> str:
    return (STATIC / "app.js").read_text(encoding="utf-8")


def _page() -> str:
    return (STATIC / "index.html").read_text(encoding="utf-8")


def _python() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in SOURCE.rglob("*.py"))


def _used() -> set[str]:
    keys = set(re.findall(r'"([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+)"', _script()))
    keys |= set(re.findall(r'data-i18n(?:-title|-aria-label)?="([^"]+)"', _page()))
    # A refusal from the server is `StepError("code")` or `AccountError("code")`,
    # worded as `error.code`.
    keys |= {
        f"error.{code}"
        for code in re.findall(r'(?:StepError|AccountError)\(\s*"([a-z_]+)"', _python())
    }
    return keys


def _placeholders(value) -> set[str]:
    texts = value.values() if isinstance(value, dict) else [value]
    return {name for text in texts for name in re.findall(r"\{(\w+)\}", text)}


def test_every_key_the_interface_uses_exists_in_english():
    assert sorted(_used() - set(_english())) == []


def test_every_english_key_is_used():
    assert sorted(set(_english()) - _used()) == []


def test_keys_are_written_out_never_assembled():
    assert re.findall(r'(?<![\w.$])t\((?!")[^)]*\)', _script()) == []


def test_server_refusals_are_written_out_never_assembled():
    assert re.findall(r'raise (?:StepError|AccountError)\((?!\s*")', _python()) == []


def test_the_page_carries_no_words_of_its_own():
    """Only the name, which is a name."""

    class Words(HTMLParser):
        def __init__(self):
            super().__init__()
            self.found: list[str] = []

        def handle_data(self, data):
            if data.strip():
                self.found.append(data.strip())

    parser = Words()
    parser.feed(_page())
    assert set(parser.found) <= {"Luikki"}


@pytest.mark.parametrize("path", sorted(LOCALES.glob("*.json")), ids=lambda path: path.name)
def test_a_locale_agrees_with_english(path):
    english = _english()
    locale = _load(path)
    assert sorted(set(locale) - set(english)) == [], "keys English does not have"

    missing = sorted(set(english) - set(locale))
    if missing:
        # Allowed: the interface falls back to English, key by key.
        warnings.warn(f"{path.name} has no translation yet for {len(missing)} keys, e.g. {missing[:5]}")

    for key, value in locale.items():
        if isinstance(value, dict):
            assert "other" in value and set(value) <= PLURAL_FORMS, key
        else:
            assert isinstance(value, str), key
        assert _placeholders(value) == _placeholders(english[key]), key
