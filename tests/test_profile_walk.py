"""Profil durchlaufen: ``iter_workspace_actions`` kennt jede Aktion eines Arbeitsbereichs."""
from neondeck.profile.model import (
    Assignment,
    ButtonImage,
    Encoder,
    EncoderLayer,
    StateDef,
    TouchPage,
    Wheel,
    Workspace,
)
from neondeck.profile.walk import iter_dicts, iter_workspace_actions


def test_workspace_walk_yields_every_action():
    def act(n):
        return {"type": "run", "command": str(n)}

    button = Assignment(act(1), ButtonImage(), act(2), act(3), [StateDef(action=act(4))])
    ws = Workspace("w", "W", [TouchPage("p", "P", [button] + [None] * 11)],
                   encoders=[Encoder(act(5), act(6), "", act(7), act(8), tap=act(9),
                                     layers=[EncoderLayer(act(10), act(11), act(12), act(13))])],
                   wheel=Wheel(act(14), left=act(15), right=act(16), tap=act(17)),
                   sticky={0: Assignment(act(18))})
    commands = {a["command"] for a in iter_workspace_actions(ws) if a}
    assert commands == {str(n) for n in range(1, 19)}
    assert len(list(iter_dicts(ws.to_json()))) > 18  # auch das JSON-Gegenstueck ist durchlaufbar
