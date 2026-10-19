"""Mehrsprachigkeit: ``core.i18n`` (Datei, Rueckfall, Platzhalter) und Vollstaendigkeit der
mitgelieferten Sprachdateien (``tools/i18n.py``)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from neondeck.core import i18n

ROOT = Path(__file__).resolve().parents[1]


def _tool():
    spec = importlib.util.spec_from_file_location("tools_i18n", ROOT / "tools" / "i18n.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tr_file_fallback_and_placeholders(tmp_path, monkeypatch):
    (tmp_path / "xx.json").write_text(json.dumps({
        "_meta": {"name": "Testisch", "code": "xx"},
        "Profil {name} geladen": "Profile {name} loaded",
        "Leer": "",
    }), encoding="utf-8")
    monkeypatch.setattr(i18n, "i18n_dir", lambda: tmp_path)
    assert i18n.available() == [("de", "Deutsch"), ("xx", "Testisch")]
    assert i18n.set_language("xx") == "xx"
    assert i18n.tr("Profil {name} geladen", name="A") == "Profile A loaded"
    assert i18n.tr("Leer") == "Leer"                           # leerer Wert: Deutsch
    assert i18n.tr("Fehlt {n} von {m}", n=1) == "Fehlt 1 von {m}"  # kein Absturz
    monkeypatch.setenv("LANG", "zz_ZZ.UTF-8")
    assert i18n.set_language("auto") == "de"                   # unbekannte Systemsprache


def test_language_files_complete():
    tool = _tool()
    texts = tool.extract()
    for code in ("en", "fr"):
        catalog = json.loads((ROOT / "data" / "i18n" / f"{code}.json").read_text("utf-8"))
        missing, mismatched, _stale = tool.compare(texts, catalog)
        assert (code, missing, mismatched) == (code, [], [])
