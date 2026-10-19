"""Vorlagen: gueltig, ins Profil einfuegen, nur die Seiten in den offenen Arbeitsbereich."""
import json

import pytest

from neondeck import actions  # noqa: F401 - registriert alle Aktionen
from neondeck.actions.base import registry
from neondeck.editor.dialogs.template_picker import TemplateChooser
from neondeck.profile import templates
from neondeck.profile.model import (
    Assignment,
    TouchPage,
    Workspace,
    empty_profile,
    validate_profile_json,
)
from support.waiting import wait_until

pytestmark = pytest.mark.usefixtures("no_modal_error")


def _actions(node) -> list:
    """Alle Aktionen (Objekte mit ``type``) eines Profil-JSON, ohne Zustandsquellen."""
    out = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "state_source":
                continue
            if isinstance(value, dict) and isinstance(value.get("type"), str):
                out.append(value)
            out.extend(_actions(value))
    elif isinstance(node, list):
        for item in node:
            out.extend(_actions(item))
    return out


def test_templates_valid_v2():
    infos = templates.list_templates()
    assert {t.name for t in infos} == {"Medien & Lautstärke", "KDE Fenster & Arbeitsflächen",
                                       "Entwickler (Konsole, Git, Editor)",
                                       "Streaming (OBS-Kürzel)",
                                       "Grafik (GIMP, Inkscape, Blender)",
                                       "Gaming (Steam, Lutris, Discord)",
                                       "Konsole & Admin (Konsole, htop, dnf)",
                                       "Blender (3D)",
                                       "Browser (Brave, Firefox)",
                                       "Büro (LibreOffice, Thunderbird)",
                                       "CADCraft (ArtCraft)",
                                       "DeckCraft (ArtCraft)",
                                       "DesignCraft (ArtCraft)",
                                       "EffectCraft (ArtCraft)",
                                       "Fenster & Monitore (KDE Plasma)",
                                       "FigCraft (ArtCraft)",
                                       "FilmCraft (ArtCraft)",
                                       "Fotos (darktable, digiKam)",
                                       "GridCraft (ArtCraft)",
                                       "Videokonferenz (Zoom, Teams, Jitsi, Discord)",
                                       "LightCraft (ArtCraft)",
                                       "PdfCraft (ArtCraft)",
                                       "PhotoCraft (ArtCraft)",
                                       "Smart Home (Home Assistant)",
                                       "SoundCraft (ArtCraft)",
                                       "System & Werkzeuge (KDE Plasma)",
                                       "Textbausteine (Mail, Briefe)",
                                       "Unreal Engine (Editor)",
                                       "VectorCraft (ArtCraft)",
                                       "Videoschnitt (Kdenlive, DaVinci Resolve)",
                                       "WordCraft (ArtCraft)",
                                       "Ziffernblock (Rechnen, Zahlen)"}
    for info in infos:
        data = templates.load_template(info.id)
        assert data["version"] == 2 and info.description
        assert validate_profile_json(data) == [], info.id
        text = json.dumps(data)
        refs = [r for r in text.split('"icon": ')[1:] if not r.startswith("null")]
        assert all(r.startswith('"svg:icons/') for r in refs), info.id  # CC0-Symbole oder Text
        for action in _actions(data):  # nur Aktionen, die es gibt, mit bekannten Feldern
            at = registry().get(action["type"])
            assert at is not None, (info.id, action)
            assert set(action) - {"type"} <= {p.name for p in at.params}, (info.id, action)
        p = templates.instantiate(info.id, existing={info.id})
        assert p.id.startswith(info.id + "-") and p.name == info.name
        assert validate_profile_json(p.to_json()) == []
        assert any(b is not None for b in p.workspaces[0].touch_pages[0].buttons)
    with pytest.raises(ValueError):
        templates.load_template("../settings")


def test_insert_templates_into_profile():
    p = empty_profile("mein", "Mein Profil")
    p.workspaces[0].name = "Medien"
    used = {c for c in range(7, 15) if c != 13}  # nur noch Taste 13 frei
    for c in used:
        p.round[c] = Assignment({"type": "hotkey", "keys": "KEY_A"})
    out = templates.insert_into(p, ["medien", "gaming"])
    assert [i.name for i in out] == ["Medien 2", "Gaming"]
    assert out[0].round_code == 13 and out[1].round_code is None
    assert p.round[13].action == {"type": "workspace", "id": out[0].workspace_id}
    assert len({w.id for w in p.workspaces}) == 3 and validate_profile_json(p.to_json()) == []
    assert p.workspaces[2].touch_pages[0].buttons[0].action["type"] == "app_focus"
    with pytest.raises(ValueError):
        templates.insert_into(p, ["gaming", "gibtsnicht"])
    assert len(p.workspaces) == 3  # nichts halb eingefuegt


def test_insert_template_pages_into_open_workspace(editor_service, editor):
    ws = Workspace("w1", "W1", [TouchPage(i, i.upper()) for i in ("a", "b", "c")])
    ws.touch_pages[1].folder = True
    names = templates.insert_pages(ws, ["grafik", "gaming"])
    assert names == ["Grafik", "Gaming"] and len(ws.touch_pages) == 5
    assert len({p.id for p in ws.touch_pages}) == 5
    with pytest.raises(ValueError):
        templates.insert_pages(ws, ["gibtsnicht"])
    assert len(ws.touch_pages) == 5

    chooser = TemplateChooser()
    try:
        chooser.search.setText("steam discord")
        assert chooser.visible_ids() == ["gaming"]
        chooser.choose(["gaming", "grafik"])
        assert set(chooser.chosen()) == {"gaming", "grafik"}
    finally:
        chooser.deleteLater()

    win = editor.window
    before = len(win.shown_ctx().workspace.touch_pages)
    assert win.extras.insert_template_pages(["grafik"]) == ["Grafik"]
    pid, ws_id = win.profile.id, win.shown_ctx().workspace.id
    stored = lambda: next(w for w in editor_service.store.load(pid).workspaces  # noqa: E731 - kurze Hilfe im Test
                          if w.id == ws_id)
    assert wait_until(lambda: len(stored().touch_pages) == before + 1)
    assert win.undoing.stack().undo_label() == "Vorlagen-Seiten einfügen"
