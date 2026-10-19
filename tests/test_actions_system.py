import threading
import time

import pytest

from neondeck.actions import execute, registry
from neondeck.actions.base import Executor
from neondeck.device.layout import ControlRef
from support.fakes import FakePopen, FakeProc, make_ctx
from support.waiting import wait_until


def test_registry_has_types():
    assert {"run", "open", "command"} <= registry().keys()


def test_run_argv():
    rec = FakePopen()
    r = execute({"type": "run", "command": "firefox --new-window"}, make_ctx(popen=rec))
    assert r.ok
    argv, kw = rec.calls[0]
    assert argv == ["firefox", "--new-window"]
    assert kw["start_new_session"] is True


def test_run_missing_program():
    r = execute({"type": "run", "command": "nix"}, make_ctx(popen=FakePopen(missing=("nix",))))
    assert not r.ok and "nicht gefunden" in r.message


def test_run_release_does_nothing():
    rec = FakePopen()
    r = execute({"type": "run", "command": "firefox"}, make_ctx(popen=rec), pressed=False)
    assert r.ok and rec.calls == []


def test_command_terminal_hold():
    rec = FakePopen()
    execute({"type": "command", "command": "ip -c a", "terminal": True, "hold": True}, make_ctx(popen=rec))
    assert rec.calls[0][0] == ["konsole", "--hold", "-e", "bash", "-lc", "ip -c a"]


def test_command_empty_opens_konsole():
    rec = FakePopen()
    execute({"type": "command", "command": "", "terminal": True}, make_ctx(popen=rec))
    assert rec.calls[0][0] == ["konsole"]


def test_command_workdir():
    rec = FakePopen()
    execute({"type": "command", "command": "ls", "workdir": "/tmp"}, make_ctx(popen=rec))
    assert rec.calls[0][0] == ["konsole", "--workdir", "/tmp", "-e", "bash", "-lc", "ls"]


def test_command_silent_logs_nonzero(caplog):
    rec = FakePopen(code=3)
    with caplog.at_level("WARNING"):
        r = execute({"type": "command", "command": "false", "terminal": False}, make_ctx(popen=rec))
        assert r.ok
        assert rec.calls[0][0] == ["bash", "-lc", "false"]
        for t in threading.enumerate():
            if t.name == "command-wait":
                t.join(2)
    assert "3" in caplog.text


def test_open_url():
    rec = FakePopen()
    execute({"type": "open", "target": "https://x.com"}, make_ctx(popen=rec))
    assert rec.calls[0][0] == ["xdg-open", "https://x.com"]


def test_unknown_type():
    r = execute({"type": "gibtsnicht"}, make_ctx(popen=FakePopen()))
    assert not r.ok and "Unbekannte Aktion" in r.message


def test_executor_does_not_block():
    """``submit`` kehrt zurueck, waehrend die Aktion noch laeuft; eine andere Taste ueberholt.
    Die langsame Aktion haengt an einem Riegel statt an einer Uhr (robust unter Last)."""
    release = threading.Event()
    slow_done = threading.Event()

    def popen(argv, **kw):
        if argv[0] == "slow":
            release.wait(15)
            slow_done.set()
        return FakeProc()

    done = []
    ev = threading.Event()

    def on_result(ref, res):
        done.append(ref.index)
        if len(done) == 2:
            ev.set()

    ex = Executor(make_ctx(popen=popen), on_result)
    try:
        ex.submit(ControlRef("square", 1), {"type": "run", "command": "slow"})
        ex.submit(ControlRef("square", 2), {"type": "run", "command": "fast"})
        assert not slow_done.is_set()  # beide submit zurueck, die langsame haengt noch
        assert wait_until(lambda: done == [2])  # die andere Taste ist schon fertig
        release.set()
        assert ev.wait(15)
        assert done == [2, 1]
    finally:
        release.set()
        ex.shutdown()


def test_executor_same_control_runs_in_order():
    """Druecken/Loslassen derselben Taste duerfen sich nicht ueberholen (R9)."""
    other_done = threading.Event()  # die langsame Aktion endet erst nach der anderen Taste

    class Slow(FakePopen):
        def __call__(self, argv, **kw):
            other_done.wait(15)
            return super().__call__(argv, **kw)

    slow = Slow()
    fast = FakePopen()
    ctx = make_ctx(popen=lambda argv, **kw: (slow if argv[0] == "slow" else fast)(argv, **kw))
    done = []
    ev = threading.Event()

    def on_result(ref, res):
        done.append((ref.index, len(slow.calls), len(fast.calls)))
        if ref.index == 2:
            other_done.set()
        if len(done) == 3:
            ev.set()

    ex = Executor(ctx, on_result)
    ref = ControlRef("square", 1)
    ex.submit(ref, {"type": "run", "command": "slow"})
    ex.submit(ref, {"type": "run", "command": "fast"})
    ex.submit(ControlRef("square", 2), {"type": "run", "command": "fast"})
    assert ev.wait(15)
    ex.shutdown()
    # andere Taste laeuft parallel und ist zuerst fertig; gleiche Taste in Reihenfolge
    assert done[0][0] == 2
    assert [d[0] for d in done[1:]] == [1, 1]
    assert done[1][1] == 1 and done[2][1:] == (1, 2)


def test_executor_logs_failure(caplog):
    got = []
    ex = Executor(make_ctx(popen=FakePopen()), lambda ref, r: got.append(r))
    with caplog.at_level("WARNING"):
        ex.submit(ControlRef("square", 0), {"type": "nope"})
        ex.shutdown()
    assert got and not got[0].ok and "Unbekannte" in caplog.text


def _wait_results(got, n, timeout=15):
    t0 = time.monotonic()
    while len(got) < n and time.monotonic() - t0 < timeout:
        time.sleep(0.01)
    return got


def test_executor_failed_pool_submit_leaves_no_orphan_lane():
    got = []
    ex = Executor(make_ctx(popen=FakePopen()), lambda ref, r: got.append(r))
    real = ex._pool.submit

    def broken(*a, **kw):
        raise RuntimeError("cannot schedule new futures after shutdown")

    ex._pool.submit = broken
    ref = ControlRef("square", 3)
    with pytest.raises(RuntimeError):
        ex.submit(ref, {"type": "run", "command": "a"})
    ex._pool.submit = real
    ex.submit(ref, {"type": "run", "command": "b"})  # Spur darf nicht verwaist sein
    assert len(_wait_results(got, 1)) == 1
    ex.shutdown()


def test_executor_lane_survives_escaping_error(caplog):
    got = []
    ex = Executor(make_ctx(popen=FakePopen()), lambda ref, r: got.append(r))
    ref = ControlRef("square", 4)
    with caplog.at_level("ERROR"):
        ex.submit(ref, None)  # kein dict: execute() wirft
        ex.submit(ref, {"type": "run", "command": "b"})
        assert len(_wait_results(got, 1)) == 1
        ex.shutdown()
    assert got[0].ok
    assert "Aktion" in caplog.text


@pytest.mark.parametrize("action", [
    {"type": "run", "command": "true"},
    {"type": "command", "command": "true", "terminal": False}])
def test_missing_workdir_reported_as_such(tmp_path, action):
    """F4: fehlender Arbeitsordner ist kein „Programm nicht gefunden“ (echtes Popen: das
    Kind scheitert schon am chdir, es startet nichts)."""
    import subprocess

    missing = str(tmp_path / "weg")
    r = execute(dict(action, workdir=missing), make_ctx(popen=subprocess.Popen))
    assert not r.ok
    assert r.message == f"Arbeitsordner nicht gefunden: {missing}"
