"""Two streams of paid runs at once (PREREG §0.3 line 15, §12): the guard's stream check,
spend reservations that keep two overlapping runs from sharing the same room under a block's
max_usd or a phase cap, and results/costs.csv appends from two processes at the same moment.
The process tests start real subprocesses. Every lock, ledger and reservation is in a
temporary folder; no test spends anything or touches the git common directory."""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import textwrap
import time
from decimal import Decimal
from pathlib import Path

import pytest

from common import approval, costs, hold, paidlock
from common.approval import ALLOW_ENV, PaidApproval, PaidCallsNotAllowed
from common.paidlock import ARC, PERSISTGYM
from common.tests.gitrepo import FROZEN_PREREG, approval_line, guarded_repo

REPO_ROOT = Path(__file__).resolve().parents[2]
BOTH = ("toggle_pilot", "replay_probe", "arc_pilot", "gemini_probe")   # a block-1-like list


@pytest.fixture
def armed(monkeypatch):
    monkeypatch.setenv(ALLOW_ENV, "1")


def _repo(tmp_path: Path, *blocks: tuple[str, str]) -> Path:
    """A guarded repo with a frozen, merged PREREG approving each (block, max_usd) for the
    experiments of both streams."""
    repo = tmp_path / "repo"
    repo.mkdir()
    text = "# Decisions log\n\n" + "".join(approval_line(name, BOTH, max_usd) + "\n"
                                           for name, max_usd in blocks)
    return guarded_repo(repo, prereg=FROZEN_PREREG, decisions=text)


def _costs(tmp_path: Path, *rows: dict) -> Path:
    p = tmp_path / "costs.csv"
    p.write_text(",".join(costs.COLUMNS) + "\n", encoding="utf-8")
    for r in rows:
        costs.append_row(r, p)
    return p


def _row(run_id: str, block: str, billed: str, experiment: str = "arc_pilot") -> dict:
    return {**{c: "" for c in costs.COLUMNS}, "timestamp_utc": f"2026-10-03T{run_id}",
            "run_id": run_id, "experiment": experiment, "cost_usd_list": billed,
            "cost_usd_billed_est": billed, "notes": approval.spend_tag(block)}


class Streams:
    """Both streams' locks in one temporary folder, as in the git common directory."""

    def __init__(self, tmp_path: Path, repo: Path, costs_csv: Path) -> None:
        self.folder = tmp_path / "gitdir"
        self.folder.mkdir()
        self.repo, self.costs = repo, costs_csv

    def lock(self, stream: str) -> Path:
        return self.folder / paidlock.lock_name(stream)

    def require(self, held: paidlock.HeldLock, *, block: str, experiment: str,
                planned: float) -> PaidApproval:
        return approval.require_paid_run(lock=held, approved_block=block,
                                         experiment=experiment, planned_usd=planned,
                                         costs_path=self.costs, repo=self.repo)


def _held(path: Path, info: dict) -> paidlock.HeldLock:
    return paidlock.HeldLock(path, info)


# ── The stream check ───────────────────────────────────────────────────

def test_a_run_must_hold_its_own_streams_lock(tmp_path, armed):
    """An ARC experiment under the PersistGym lock, or the reverse, would let two runs of
    one stream go at once: refused before anything else is read."""
    s = Streams(tmp_path, _repo(tmp_path, ("1-pilots", "70")), _costs(tmp_path))
    with paidlock.paid_run_lock(s.lock(PERSISTGYM), run_id="pg", what="x",
                                stream=PERSISTGYM) as info:
        held = _held(s.lock(PERSISTGYM), info)
        with pytest.raises(PaidCallsNotAllowed, match="experiment 'arc_pilot' runs in the arc "
                                                      "stream, but this run holds the "
                                                      "persistgym stream's lock"):
            s.require(held, block="1-pilots", experiment="arc_pilot", planned=1)
        with pytest.raises(PaidCallsNotAllowed, match="'ext_gemini_flex' has no budget phase"):
            s.require(held, block="1-pilots", experiment="ext_gemini_flex", planned=1)
        no_stream = {k: v for k, v in info.items() if k != "stream"}
        with pytest.raises(PaidCallsNotAllowed, match="names no stream"):
            s.require(_held(s.lock(PERSISTGYM), no_stream), block="1-pilots",
                      experiment="toggle_pilot", planned=1)
        assert s.require(held, block="1-pilots", experiment="toggle_pilot",
                         planned=1).stream == "persistgym"
    with (paidlock.paid_run_lock(s.lock(ARC), run_id="arc", what="x", stream=ARC) as info,
          pytest.raises(PaidCallsNotAllowed, match="'toggle_pilot' runs in the persistgym")):
        s.require(_held(s.lock(ARC), info), block="1-pilots", experiment="toggle_pilot",
                  planned=1)
    assert not any(s.folder.glob(f"{paidlock.RESERVATION_PREFIX}*"))


# ── Reservations: two runs at once cannot share the same room ──────────

def test_two_streams_cannot_together_exceed_a_blocks_max_usd(tmp_path, armed):
    """Block 1 lists experiments of both streams. While an ARC run is going, the planned
    spend it reserved counts as spent for a PersistGym run of the same block, and the
    other way round, until the run's costs row is written."""
    s = Streams(tmp_path, _repo(tmp_path, ("1-pilots", "10")), _costs(tmp_path))
    with (paidlock.paid_run_lock(s.lock(ARC), run_id="arc-1", what="arc pilot",
                                 stream=ARC) as arc_info,
          paidlock.paid_run_lock(s.lock(PERSISTGYM), run_id="pg-1", what="echo probe",
                                 stream=PERSISTGYM) as pg_info):
        arc, pg = _held(s.lock(ARC), arc_info), _held(s.lock(PERSISTGYM), pg_info)
        a = s.require(arc, block="1-pilots", experiment="arc_pilot", planned=6)
        assert (a.stream, a.reserved_block_usd, a.block_headroom_usd) == ("arc", 0, 4)
        assert paidlock.reservation_path(s.lock(ARC), ARC).exists()

        with pytest.raises(PaidCallsNotAllowed) as e:
            s.require(pg, block="1-pilots", experiment="toggle_pilot", planned=5)
        msg = str(e.value)
        assert "block '1-pilots' has spent $0.00 of its max_usd $10" in msg
        assert "reserved $6.00 of it until its costs row is written" in msg
        assert "run arc-1 (arc stream, arc_pilot, block 1-pilots, phase 0, $6.00" in msg
        assert "would exceed it by $1.00" in msg and "stop and ask the researcher" in msg
        assert not paidlock.reservation_path(s.lock(PERSISTGYM), PERSISTGYM).exists()

        p = s.require(pg, block="1-pilots", experiment="toggle_pilot", planned=4)
        assert (p.reserved_block_usd, p.reserved_phase_usd, p.block_headroom_usd) == (6, 6, 0)
        assert p.headroom_usd == pytest.approx(100 - 6 - 4)            # phase 0's cap

        # The ARC run now asks again (as a probe's next model would): the PersistGym run's
        # $4 counts against it, its own earlier reservation does not.
        assert s.require(arc, block="1-pilots", experiment="arc_pilot",
                         planned=6).block_headroom_usd == 0
        with pytest.raises(PaidCallsNotAllowed, match=r"reserved \$4.00 of it"):
            s.require(arc, block="1-pilots", experiment="arc_pilot", planned=6.01)

        # The ARC run ends: row, last-run record, then the reservation goes. Its $2.50 spent
        # counts from now on, not its $6 planned.
        costs.append_row(_row("arc-1", "1-pilots", "2.50"), s.costs)
        paidlock.record_last_run(s.lock(ARC), stream=ARC, run_id="arc-1", costs_csv=s.costs,
                                 timestamp_utc="2026-10-03Tarc-1")
        assert paidlock.release_reservation(s.lock(ARC), stream=ARC, token=arc_info["token"])
        assert s.require(pg, block="1-pilots", experiment="toggle_pilot",
                         planned=7.5).block_headroom_usd == 0
        with pytest.raises(PaidCallsNotAllowed, match=r"spent \$2.50 of its max_usd \$10; "
                                                      r"planned \$7.51"):
            s.require(pg, block="1-pilots", experiment="toggle_pilot", planned=7.51)
    assert not any(s.folder.glob(f"{paidlock.RESERVATION_PREFIX}*"))


def test_two_streams_cannot_together_exceed_a_phase_cap(tmp_path, armed):
    """Phases 0 and 2 have runs of both streams. Two runs in different blocks of one phase
    count each other's reservation against the phase cap only (PREREG §12 'Operational')."""
    s = Streams(tmp_path, _repo(tmp_path, ("arc-blk", "1000"), ("pg-blk", "1000")),
                _costs(tmp_path, _row("old", "arc-blk", "30")))
    with (paidlock.paid_run_lock(s.lock(ARC), run_id="arc-1", what="x", stream=ARC) as ai,
          paidlock.paid_run_lock(s.lock(PERSISTGYM), run_id="pg-1", what="y",
                                 stream=PERSISTGYM) as pi):
        arc, pg = _held(s.lock(ARC), ai), _held(s.lock(PERSISTGYM), pi)
        a = s.require(arc, block="arc-blk", experiment="gemini_probe", planned=40)
        assert a.headroom_usd == pytest.approx(100 - 30 - 40)
        with pytest.raises(PaidCallsNotAllowed) as e:
            s.require(pg, block="pg-blk", experiment="replay_probe", planned=31)
        msg = str(e.value)
        assert "planned $31.00 would exceed the phase 0 cap of $100 by $1.00" in msg
        assert "counting phase spend $30.00 and $40.00 reserved" in msg
        assert "run arc-1 (arc stream, gemini_probe, block arc-blk, phase 0" in msg
        p = s.require(pg, block="pg-blk", experiment="replay_probe", planned=30)
        assert (p.reserved_block_usd, p.reserved_phase_usd) == (0, 40)   # other block
        assert p.headroom_usd == pytest.approx(0) and p.block_headroom_usd == 970


def test_a_reservation_in_another_block_and_phase_takes_no_room(tmp_path, armed):
    s = Streams(tmp_path, _repo(tmp_path, ("arc-blk", "10"), ("pg-blk", "10")),
                _costs(tmp_path))
    pg_lock = s.lock(PERSISTGYM)
    with paidlock.paid_run_lock(pg_lock, run_id="pg-1", what="y", stream=PERSISTGYM) as pi:
        with paidlock.budget_mutex(pg_lock):    # a PersistGym run in phase 1a, other block
            paidlock.write_reservation(_held(pg_lock, pi), approved_block="3-persistgym",
                                       experiment="persistgym", phase="1a",
                                       planned_usd=Decimal(450))
        with paidlock.paid_run_lock(s.lock(ARC), run_id="arc-1", what="x", stream=ARC) as ai:
            a = s.require(_held(s.lock(ARC), ai), block="arc-blk",
                          experiment="arc_pilot", planned=10)
            assert (a.reserved_block_usd, a.reserved_phase_usd) == (0, 0)


def test_a_left_over_reservation_of_the_runs_own_stream_refuses(tmp_path, armed):
    """A reservation of this run's stream that this run did not write belongs to a run that
    did not end cleanly: it is refused until the operator deletes it."""
    s = Streams(tmp_path, _repo(tmp_path, ("1-pilots", "70")), _costs(tmp_path))
    with paidlock.paid_run_lock(s.lock(ARC), run_id="crashed", what="x", stream=ARC) as info:
        with paidlock.budget_mutex(s.lock(ARC)):
            left = paidlock.write_reservation(_held(s.lock(ARC), info),
                                              approved_block="1-pilots",
                                              experiment="arc_pilot", phase="0",
                                              planned_usd=Decimal(15))
        paidlock.keep(s.lock(ARC), info, "add its row by hand")
    s.lock(ARC).unlink()                                 # the operator deleted the lock only
    with paidlock.paid_run_lock(s.lock(ARC), run_id="next", what="x", stream=ARC) as info:
        with pytest.raises(PaidCallsNotAllowed) as e:
            s.require(_held(s.lock(ARC), info), block="1-pilots", experiment="arc_pilot",
                      planned=1)
        msg = str(e.value)
        assert "a spend reservation of the arc stream is left over: run crashed" in msg
        assert "approved_block=1-pilots;" in msg and f"delete {left.path} by hand" in msg
        assert left.path.exists()                                    # left for the operator
        # the other stream's runs keep counting it meanwhile
    with paidlock.paid_run_lock(s.lock(PERSISTGYM), run_id="pg", what="y",
                                stream=PERSISTGYM) as info:
        p = s.require(_held(s.lock(PERSISTGYM), info), block="1-pilots",
                      experiment="toggle_pilot", planned=1)
        assert p.reserved_block_usd == 15
    left.path.unlink()
    with paidlock.paid_run_lock(s.lock(ARC), run_id="next", what="x", stream=ARC) as info:
        assert s.require(_held(s.lock(ARC), info), block="1-pilots", experiment="arc_pilot",
                         planned=1).reserved_block_usd == 0


def test_an_unreadable_reservation_refuses(tmp_path, armed):
    s = Streams(tmp_path, _repo(tmp_path, ("1-pilots", "70")), _costs(tmp_path))
    paidlock.reservation_path(s.lock(ARC), ARC).write_text('{"run_id": "x"', encoding="utf-8")
    with (paidlock.paid_run_lock(s.lock(PERSISTGYM), run_id="pg", what="y",
                                 stream=PERSISTGYM) as info,
          pytest.raises(PaidCallsNotAllowed, match="unreadable.*its run's planned spend "
                                                   "cannot be counted")):
        s.require(_held(s.lock(PERSISTGYM), info), block="1-pilots",
                  experiment="toggle_pilot", planned=1)


def test_a_hold_placed_while_the_run_is_checked_refuses(tmp_path, armed, monkeypatch):
    """A run of the other stream that ends COST_CAP while this run's checks are under way
    (after the hold check, before the reservation) still stops this run (PREREG §7.7)."""
    s = Streams(tmp_path, _repo(tmp_path, ("1-pilots", "70")), _costs(tmp_path))
    real = approval.prereg_not_frozen

    def meanwhile(repo, remote=approval.MAIN):
        hold.place_hold(s.lock(PERSISTGYM), run_id="arc-capped", experiment="arc_path",
                        reason="ended COST_CAP")
        return real(repo, remote)
    monkeypatch.setattr(approval, "prereg_not_frozen", meanwhile)
    with (paidlock.paid_run_lock(s.lock(PERSISTGYM), run_id="pg", what="y",
                                 stream=PERSISTGYM) as info,
          pytest.raises(PaidCallsNotAllowed, match="a hold was placed while this run was "
                                                   "being checked, by arc-capped")):
        s.require(_held(s.lock(PERSISTGYM), info), block="1-pilots",
                  experiment="toggle_pilot", planned=1)
    assert not any(s.folder.glob(f"{paidlock.RESERVATION_PREFIX}*"))


def test_a_row_written_while_the_run_is_checked_counts(tmp_path, armed, monkeypatch):
    """The other stream's run may write its row (and drop its reservation) after this run's
    first spend check: the check under the mutex reads the ledger again, so that spend counts
    against the block before this run reserves."""
    s = Streams(tmp_path, _repo(tmp_path, ("1-pilots", "10")), _costs(tmp_path))
    real = approval.prereg_not_frozen

    def meanwhile(repo, remote=approval.MAIN):
        costs.append_row(_row("arc-1", "1-pilots", "8"), s.costs)
        return real(repo, remote)
    monkeypatch.setattr(approval, "prereg_not_frozen", meanwhile)
    with (paidlock.paid_run_lock(s.lock(PERSISTGYM), run_id="pg", what="y",
                                 stream=PERSISTGYM) as info,
          pytest.raises(PaidCallsNotAllowed) as e):
        s.require(_held(s.lock(PERSISTGYM), info), block="1-pilots",
                  experiment="toggle_pilot", planned=5)
    assert str(e.value) == ("block '1-pilots' has spent $8.00 of its max_usd $10; planned "
                            "$5.00 would exceed it by $3.00: stop and ask the researcher")
    assert not any(s.folder.glob(f"{paidlock.RESERVATION_PREFIX}*"))


def test_the_last_run_of_the_other_stream_is_checked_under_the_mutex(tmp_path, armed,
                                                                     monkeypatch):
    """A run of the other stream that ends in another checkout between this run's first
    ledger check and its reservation writes its record before it removes its reservation;
    the check under the mutex sees the record, so the spend is not lost."""
    s = Streams(tmp_path, _repo(tmp_path, ("1-pilots", "70")), _costs(tmp_path))
    real = approval.prereg_not_frozen

    def meanwhile(repo, remote=approval.MAIN):
        paidlock.record_last_run(s.lock(ARC), stream=ARC, run_id="arc-elsewhere",
                                 costs_csv=tmp_path / "other" / "costs.csv")
        return real(repo, remote)
    monkeypatch.setattr(approval, "prereg_not_frozen", meanwhile)
    with (paidlock.paid_run_lock(s.lock(PERSISTGYM), run_id="pg", what="y",
                                 stream=PERSISTGYM) as info,
          pytest.raises(PaidCallsNotAllowed, match="arc stream, arc-elsewhere.*not in "
                                                   "this checkout")):
        s.require(_held(s.lock(PERSISTGYM), info), block="1-pilots",
                  experiment="toggle_pilot", planned=1)


# ── Real processes ─────────────────────────────────────────────────────

def _spawn(code: str, *args: str) -> subprocess.Popen:
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    return subprocess.Popen([sys.executable, "-c", textwrap.dedent(code), *args],
                            cwd=REPO_ROOT, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, encoding="utf-8")


def _wait_for(paths: list[Path], procs: list[subprocess.Popen], timeout_s: float = 60):
    deadline = time.monotonic() + timeout_s
    while not all(p.exists() for p in paths):
        for proc in procs:
            if proc.poll() is not None and proc.returncode != 0:
                raise AssertionError(f"a child failed: {proc.communicate()}")
        assert time.monotonic() < deadline, "children did not get ready"
        time.sleep(0.01)


def _finish(procs: list[subprocess.Popen]) -> list[str]:
    outs = []
    for proc in procs:
        out, err = proc.communicate(timeout=120)
        assert proc.returncode == 0, err
        outs.append(out)
    return outs


APPENDER = """
    import sys, time
    from pathlib import Path
    from common import costs
    path, who, n, ready, go = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4], sys.argv[5]
    row = {c: "" for c in costs.COLUMNS}
    Path(ready).touch()
    while not Path(go).exists():
        time.sleep(0.001)
    for i in range(n):
        # notes far longer than one write buffer, so an unguarded append could interleave
        costs.append_row({**row, "run_id": f"{who}-{i}", "experiment": "arc_pilot"
                          if who == "arc" else "toggle_pilot", "cost_usd_list": "0.01",
                          "cost_usd_billed_est": "0.01",
                          "notes": f"approved_block=b; {who}-{i} " + who[0] * 20000}, Path(path))
"""

READER = """
    import sys, time
    from pathlib import Path
    from common import costs
    path, ready, go, stop = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    Path(ready).touch()
    while not Path(go).exists():
        time.sleep(0.001)
    reads = 0
    while not Path(stop).exists():
        for r in costs.read_rows(Path(path)):   # every row whole, or the run would refuse
            who, i = r["run_id"].split("-")
            assert r["notes"] == f"approved_block=b; {who}-{i} " + who[0] * 20000, r["run_id"]
            assert r["cost_usd_billed_est"] == "0.01"
        reads += 1
    print(reads)
"""


def test_two_processes_append_to_the_ledger_at_once(tmp_path):
    """An ARC run and a PersistGym run may write their costs rows at the same moment, in the
    same checkout. Two real processes append 150 long rows each, started together, while a
    third reads the ledger over and over: every row arrives whole and in one piece, none is
    lost, and no read ever sees half a row."""
    ledger = _costs(tmp_path)
    n = 150
    ready = [tmp_path / f"ready-{i}" for i in range(3)]
    go, stop = tmp_path / "go", tmp_path / "stop"
    writers = [_spawn(APPENDER, str(ledger), who, str(n), str(ready[i]), str(go))
               for i, who in enumerate((ARC, PERSISTGYM))]
    reader = _spawn(READER, str(ledger), str(ready[2]), str(go), str(stop))
    _wait_for(ready, [*writers, reader])
    go.touch()
    _finish(writers)
    stop.touch()
    (reads,) = _finish([reader])
    assert int(reads) >= 1

    rows = costs.read_rows(ledger)
    assert len(rows) == 2 * n
    for who in (ARC, PERSISTGYM):
        mine = [r for r in rows if r["run_id"].startswith(f"{who}-")]
        assert [r["run_id"] for r in mine] == [f"{who}-{i}" for i in range(n)]  # in order
        assert all(r["notes"] == f"approved_block=b; {r['run_id']} " + who[0] * 20000
                   for r in mine)
    # nothing but whole rows: the raw file has exactly the header and 2n records
    with ledger.open(newline="", encoding="utf-8") as f:
        assert sum(1 for _ in csv.reader(f)) == 1 + 2 * n
    assert costs.spend_by_phase(rows)["0"] == pytest.approx(0.01 * 2 * n)


RESERVER = """
    import json, sys, time
    from decimal import Decimal
    from pathlib import Path
    from common import approval, paidlock
    from common.approval import PaidApproval, PaidCallsNotAllowed
    folder, stream, experiment, costs_csv, ready, go, out, end = sys.argv[1:9]
    lock = Path(folder) / paidlock.lock_name(stream)
    granted = PaidApproval("shared", experiment, "0", 6.0, 0.0, "1.0", Path(costs_csv),
                           ("arc_pilot", "toggle_pilot"), 10.0)
    with paidlock.paid_run_lock(lock, run_id=f"{stream}-run", what="race",
                                stream=stream) as info:
        Path(ready).touch()
        while not Path(go).exists():
            time.sleep(0.0005)
        try:
            r = approval.reserve_spend(paidlock.HeldLock(lock, info), granted)
            result = {"reserved": True, "reserved_block_usd": r.reserved_block_usd}
        except PaidCallsNotAllowed as e:
            result = {"reserved": False, "why": str(e)}
        Path(out).write_text(json.dumps(result), encoding="utf-8")
        while not Path(end).exists():     # keep the lock, and any reservation, until told
            time.sleep(0.005)
"""


@pytest.mark.parametrize("round_", range(4))
def test_two_processes_cannot_both_reserve_the_same_room(tmp_path, round_):
    """The race the budget mutex closes: an ARC run and a PersistGym run of one block reach
    their reservation step at the same moment, each planning $6 of a $10 block. Each reads
    the other's reservation and writes its own under the one operating-system lock, so
    exactly one gets the room, whatever the timing."""
    folder = tmp_path / "gitdir"
    folder.mkdir()
    ledger = _costs(tmp_path)
    ready = [tmp_path / f"ready-{s}" for s in paidlock.STREAMS]
    outs = [tmp_path / f"out-{s}.json" for s in paidlock.STREAMS]
    go, end = tmp_path / "go", tmp_path / "end"
    procs = [_spawn(RESERVER, str(folder), stream, experiment, str(ledger), str(ready[i]),
                    str(go), str(outs[i]), str(end))
             for i, (stream, experiment) in enumerate(((ARC, "arc_pilot"),
                                                       (PERSISTGYM, "toggle_pilot")))]
    _wait_for(ready, procs)
    go.touch()
    _wait_for(outs, procs)
    results = [json.loads(p.read_text(encoding="utf-8")) for p in outs]
    end.touch()
    _finish(procs)
    assert sorted(r["reserved"] for r in results) == [False, True], results
    (loser,) = [r for r in results if not r["reserved"]]
    assert "reserved $6.00 of it" in loser["why"] and "would exceed it by $2.00" in loser["why"]
    (winner,) = [r for r in results if r["reserved"]]
    assert winner["reserved_block_usd"] == 0
    # both processes have ended: their locks and the winner's reservation are gone
    assert not any(folder.glob("persistgym-paid-run-*.lock"))
    assert not any(folder.glob(f"{paidlock.RESERVATION_PREFIX}*"))
