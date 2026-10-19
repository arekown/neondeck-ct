"""Seiten, Regler, Rad und Tasten eines Windows-Profils aufbauen."""
from __future__ import annotations

from ....core.i18n import N_, tr
from ....device.layout import ENCODERS, ROUND_CODES, SQUARE_KEY_CODES, TOUCH_BUTTONS
from ...model import (
    Assignment,
    Encoder,
    Profile,
    TouchPage,
    Wheel,
    Workspace,
    empty_profile,
)
from .actions import ActionMapper
from .context import Context, nocase
from .icons import IconReader

CLOCK_WHEEL_TEMPLATE = "wheeltoolanalogclock"


class ProfileBuilder:
    def __init__(self, ctx: Context, actions: ActionMapper, icons: IconReader):
        self.ctx = ctx
        self.actions = actions
        self.icons = icons

    # -- Tasten, Regler, Rad -----------------------------------------------------------------
    def assign(self, control: dict, where: str) -> Assignment | None:
        if control.get("fnPressAction"):
            self.ctx.note(where, tr("Fn-Belegung nicht übernommen: {action}", action=control["fnPressAction"]))
        s = control.get("pressAction")
        act = self.actions.action(s, where)
        return Assignment(act, self.icons.image(s, where)) if act is not None else None

    def keyed(self, page: dict | None, codes: range, where: str) -> dict:
        out = dict.fromkeys(codes)
        for i, control in enumerate((page or {}).get("controls") or []):
            w = f"{where} {i + 1}"
            if i < len(codes):
                out[codes[i]] = self.assign(control, w)
            elif control.get("pressAction") or control.get("fnPressAction"):
                self.ctx.note(w, tr("kein Gegenstück am CT: {action}",
                                 action=control.get("pressAction") or control.get("fnPressAction")))
        return out

    def touch_page(self, page: dict, ws_name: str, index: int) -> TouchPage:
        name = page.get("displayName") or ""
        buttons: list[Assignment | None] = [None] * TOUCH_BUTTONS
        for i, control in enumerate(page.get("controls") or []):
            where = tr("{ws} / {page} / Taste {n}", ws=ws_name, page=name, n=i + 1)
            if i < TOUCH_BUTTONS:
                buttons[i] = self.assign(control, where)
            elif control.get("pressAction"):
                self.ctx.note(where, tr("kein Platz (12 Tasten je Seite): {action}",
                              action=control["pressAction"]))
        return TouchPage(page.get("name") or f"p{index + 1}", name, buttons)

    def encoders(self, page: dict | None, ws_name: str) -> list[Encoder]:
        out = [Encoder() for _ in range(ENCODERS)]
        for i, control in enumerate((page or {}).get("controls") or []):
            if i >= ENCODERS:
                break
            where = tr("{ws} / Regler {n}", ws=ws_name, n=i + 1)
            for fn in ("fnRotateAction", "fnPressAction"):
                if control.get(fn):
                    self.ctx.note(where, tr("Fn-Belegung nicht übernommen: {action}", action=control[fn]))
            out[i] = Encoder(self.actions.action(control.get("rotateAction"), tr("{where} (Drehen)", where=where)),
                             self.actions.action(control.get("pressAction"), tr("{where} (Drücken)", where=where)),
                             self.icons.label(control.get("rotateAction"))
                             or self.icons.label(control.get("pressAction")))
        return out

    def wheel(self, page: dict | None, ws_name: str) -> Wheel:
        if page is None:
            return Wheel()
        where = tr("{ws} / Rad", ws=ws_name)
        params = nocase(page.get("parameters"))
        rotate = self.actions.action(params.get("adjustment"), where)
        template = page.get("templateName") or ""
        if template.lower() == CLOCK_WHEEL_TEMPLATE:
            return Wheel(rotate, "clock", page.get("displayName") or "")
        self.ctx.note(where, tr("Rad-Vorlage „{name}“ nicht übernommen", name=template))
        return Wheel(rotate, "label", page.get("displayName") or "")

    # -- Arbeitsbereiche und Profil ----------------------------------------------------------
    def _pages(self, by_name: dict, names: list[str] | None, ws_name: str, kind: str) -> list:
        pages = []
        for n in names or []:
            if n in by_name:
                pages.append(by_name[n])
            else:
                self.ctx.note(ws_name, tr("{kind} {name} fehlt", kind=tr(kind), name=n))
        return pages

    def workspace(self, w: dict, tables: dict[str, dict]) -> Workspace:
        ws_name = w.get("displayName") or ""
        touch = self._pages(tables["touch"], w.get("touchPageNames"), ws_name, N_("Seite"))
        pages = [self.touch_page(p, ws_name, i) for i, p in enumerate(touch)]
        enc_pages = self._pages(tables["encoders"], w.get("encoderPageNames"), ws_name,
                                N_("Reglerseite"))
        wheel_pages = self._pages(tables["wheels"], w.get("wheelPageNames"), ws_name, N_("Radseite"))
        for kind, extra in ((N_("Reglerseite"), enc_pages[1:]), (N_("Radseite"), wheel_pages[1:])):
            for p in extra:
                self.ctx.note(ws_name, tr("weitere {kind} „{name}“ nicht übernommen", kind=tr(kind),
                             name=p.get("displayName")))
        if w.get("activationActions"):
            self.ctx.note(ws_name, tr("Aktionen beim Aktivieren nicht übernommen"))
        return Workspace(
            w.get("name"), ws_name, pages or [TouchPage("p1", tr("Seite {n}", n=1))],
            self.encoders(enc_pages[0] if enc_pages else None, ws_name),
            self.wheel(wheel_pages[0] if wheel_pages else None, ws_name))

    def run(self) -> tuple[Profile, list[str]]:
        info = self.ctx.info
        layout = info.get("layout") or {}
        modes = layout.get("layoutModes") or [{}]
        for extra in modes[1:]:
            self.ctx.note(tr("Profil"), tr("Modus „{name}“ nicht übernommen",
                                                    name=extra.get("modeName")))
        mode = modes[0]
        tables = {"touch": {p.get("name"): p for p in mode.get("touchPages") or []},
                  "encoders": {p.get("name"): p for p in mode.get("encoderPages") or []},
                  "wheels": {p.get("name"): p for p in mode.get("wheelPages") or []}}
        raw_ws = mode.get("workspaces") or []
        self.ctx.workspace_ids = {w.get("name") for w in raw_ws if w.get("name")}

        workspaces = [self.workspace(w, tables) for w in raw_ws] or empty_profile().workspaces
        home = mode.get("homeWorkspaceName")
        if home not in {w.id for w in workspaces}:
            home = workspaces[0].id
        profile = Profile(
            id=info.get("name") or "windows",
            name=info.get("displayName") or tr("Windows-Profil"),
            round=self.keyed(layout.get("roundPage"), ROUND_CODES, tr("Runde Taste")),
            square=self.keyed(layout.get("squarePage"), SQUARE_KEY_CODES, tr("Eckige Taste")),
            workspaces=workspaces, home_workspace=home)
        return profile, self.ctx.messages
