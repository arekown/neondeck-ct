"""API-Methoden fuer Ansicht und Bedienung: ``view.*``, ``page``, ``trigger``, ``simulate``,
``state.set``, ``image.set``."""
from __future__ import annotations

from typing import Any

from ...actions.base import Trigger
from ...core.i18n import N_
from ...device.layout import ControlRef
from ...device.protocol import Event
from ...render.icons import load_icon
from ...render.images import TILE
from ..params import UNSET, AbsPath, Choice, Int, Obj, Ref, Spec, api_method
from ..params import Event as EventSpec
from ..protocol import ApiError, format_ref
from . import Handlers

TRIGGER_KINDS = tuple(Trigger)
PAGE_DIRS = {"next": "page_next", "prev": "page_previous"}


def _page_range(page: int, count: int) -> None:
    if not 0 <= page < count:
        raise ApiError("page.not_found", N_("Seite {page} gibt es nicht (0–{max})"),
                       {"page": page, "max": count - 1})


class ViewHandlers(Handlers):

    @api_method("view.get")
    def get(self) -> dict:
        return self.engine.view_state()

    @api_method("view.set", workspace=Spec(default=UNSET), page=Int(nullable=True))
    def set(self, workspace: Any, page: int | None) -> dict:
        e = self.engine
        ws_id = e.workspace_id if workspace is UNSET else workspace
        ws = next((w for w in e.profile.workspaces if w.id == ws_id), None)
        if ws is None:
            raise ApiError("workspace.not_found", N_("Arbeitsbereich {id!r} gibt es nicht"),
                           {"id": ws_id})
        if page is not None:
            _page_range(page, len(ws.touch_pages))
        if ws_id != e.workspace_id:
            e.call("workspace", {"id": ws_id})
        if page is not None:
            e.call("page", {"index": page})
        return e.view_state()

    @api_method("page", dir=Choice(options=tuple(PAGE_DIRS),
                                   message=N_("dir muss \"next\" oder \"prev\" sein")),
                index=Int())
    def page(self, dir: str | None, index: int | None) -> dict:
        e = self.engine
        if dir is not None:
            e.call(PAGE_DIRS[dir], {})
        elif index is not None:
            _page_range(index, e.view_state()["page_count"])
            e.call("page", {"index": index})
        else:
            raise ApiError("param.missing", N_("dir oder index fehlt"), {"name": "dir"})
        return e.view_state()

    @api_method("trigger", ref=Ref(),
                which=Choice(default=Trigger.TAP.value, options=TRIGGER_KINDS,
                             message=N_("which muss {options} sein")),
                steps=Int(),
                action=Obj(nullable=True, with_type=True,
                           message=N_("action muss ein JSON-Objekt mit \"type\" sein")))
    def trigger(self, ref: ControlRef, which: str, steps: int | None,
                action: dict | None) -> dict:
        if steps is None:
            steps = 1 if which == Trigger.ROTATE else 0
        if which == Trigger.ROTATE and steps == 0:
            raise ApiError("param.zero_steps", N_("steps darf beim Drehen nicht 0 sein"))
        # Editor „Testen“: die gezeigte, evtl. ungespeicherte Aktion. Leiste: wie am Geraet
        # eigene Tipp-Aktion oder Regler-Druck; Ergebnis und Blinken zeigt die Engine
        if action is not None:
            self.engine.trigger(ref, action, steps=steps)
        elif not self.engine.activate(ref, which, steps=steps):  # wie am Geraet (Zustaende)
            shown = format_ref(ref)
            raise ApiError("trigger.no_action", N_("Keine Aktion auf {ref} ({which})"),
                           {"ref": shown, "which": which})
        return {}

    @api_method("simulate", event=EventSpec())
    def simulate(self, event: Event) -> dict:
        self.engine.handle(event)
        return {}

    @api_method("state.set", ref=Ref(), n=Int(required=True, minimum=0))
    def state(self, ref: ControlRef, n: int) -> dict:
        self.engine.set_state(ref, n)
        return {}

    @api_method("image.set",
                ref=Ref(only="touch", only_code="image.touch_only",
                        only_message=N_("Bilder gibt es nur für Touch-Tasten (touch:0–11)")),
                path=AbsPath())
    def image(self, ref: ControlRef, path: str | None) -> dict:
        if path is not None and load_icon(f"file:{path}", TILE) is None:
            raise ApiError("image.unreadable", N_("Bild {path!r} nicht lesbar"), {"path": path})
        self.engine.set_image_override(ref, path)
        return {}
