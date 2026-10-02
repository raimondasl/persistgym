"""Parallel play (PREREG §4.6; §0.3 line 15; harnesses/parallel.py), with the fake model and no
network: parallel play writes the outputs of sequential play byte for byte, reserves spend so
that it never starts an episode its planned spend cannot hold, and its stop rules (the abort
after 2 excluded episodes, after 2 API errors, the transport's stop, an error, Ctrl+C) stop
the episodes in flight too."""

from __future__ import annotations

import copy
import gzip
import json
import threading
import time
from collections import Counter
from pathlib import Path

import httpx
import openai
import pytest

from common.costs import spend_usd
from harnesses import blinding, parallel, runner
from harnesses.cells import CELLS
from harnesses.config import HarnessConfig
from harnesses.fake import FakeModel
from harnesses.items import item_text
from harnesses.openai_transport import BudgetExceeded
from harnesses.pricing import UsageLedger
from harnesses.runner import run_batch

CFG = HarnessConfig()
WAIT_S = 60  # a gate that is not opened within this time fails the test instead of hanging


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    """Calls are timed with `runner.CLOCK`; fixed, `call_latency_s` is 0.0 in every record,
    so that sequential and parallel outputs can be compared byte for byte."""
    monkeypatch.setattr(runner, "CLOCK", lambda: 0.0)


def _reply_fn(eps):
    """Payload-only replies: look up the entity at the need step, acknowledge everything
    else. A lookup adds a turn in recoverable cells, so episodes differ in length and finish
    out of order."""
    need = {ep.steps[ep.need_step].observation: ep.entity for ep in eps}

    def reply(payload, i):
        last = item_text(payload["input"][-1])
        return f"ACTION: lookup({need[last]})" if last in need else "ACTION: ack(none)"
    return reply


def _run(eps, cid, transport, root: Path, n: int, **kw) -> dict:
    return run_batch(eps, CELLS[cid], CFG, transport, experiment=kw.pop("experiment",
                                                                         "persistgym"),
                     run_id="r", results_root=root / "results", raw_root=root / "raw",
                     parallel=n, **kw)


def _outputs(root: Path, experiment: str = "persistgym") -> dict[str, bytes]:
    out = root / "results" / experiment / "r"
    raw = root / "raw" / experiment / "r"
    with gzip.open(raw / "transcript.jsonl.gz", "rb") as f:
        transcript = f.read()
    episodes = (out if (out / "episodes.jsonl").exists() else raw) / "episodes.jsonl"
    return {"episodes.jsonl": episodes.read_bytes(), "transcript": transcript,
            "summary.json": (out / "summary.json").read_bytes()}


def _lines(root: Path, experiment: str = "persistgym") -> list[dict]:
    return [json.loads(x) for x in _outputs(root, experiment)["episodes.jsonl"].splitlines()]


def _events(root: Path) -> list[dict]:
    return [json.loads(x) for x in _outputs(root)["transcript"].splitlines()]


VOLATILE_META = {"started_utc", "finished_utc", "raw_transcript_path", "parallel"}


def _stable(meta: dict) -> dict:
    return {k: v for k, v in meta.items() if k not in VOLATILE_META}


def _canonical(payloads) -> Counter:
    return Counter(json.dumps(p, sort_keys=True) for p in payloads)


class _Gate:
    """Hold episode 0's first call until episodes 1-3 have made all their calls, so that
    they finish before it: the outputs must still come out in the run's order."""

    def __init__(self, calls_of_1_to_3: int, first_id: str, others: set[str]):
        self.needed, self.first_id, self.others = calls_of_1_to_3, first_id, others
        self.served = 0
        self.lock = threading.Lock()
        self.open = threading.Event()
        self.opened_by_count = None

    def channel(self, gate: _Gate):
        class Gated(parallel.EpisodeChannel):
            def send(self, payload):
                if self.episode_id == gate.first_id and gate.opened_by_count is None:
                    gate.opened_by_count = gate.open.wait(WAIT_S)
                response = super().send(payload)
                if self.episode_id in gate.others:
                    with gate.lock:
                        gate.served += 1
                        if gate.served >= gate.needed:
                            gate.open.set()
                return response
        return Gated


@pytest.mark.parametrize("cid", ["F-r", "W-n-0", "Σ-n-r"])
def test_parallel_outputs_are_the_sequential_outputs_byte_for_byte(small_eps, tmp_path,
                                                                   monkeypatch, cid):
    """PREREG §4.6: the same payloads and per-episode outputs, written in the same order. 24
    episodes (3 templates x 8 task cells, with lookups at recoverable need steps and, in
    Σ-n-r, summary calls), the first held back so that later ones finish first."""
    eps = small_eps
    seq_fake = FakeModel(_reply_fn(eps), ids="payload")
    seq_meta = _run(eps, cid, seq_fake, tmp_path / "seq", 1)
    seq = _outputs(tmp_path / "seq")
    n_requests = [json.loads(x)["n_requests"] for x in seq["episodes.jsonl"].splitlines()]
    assert len(n_requests) == len(eps) and len(set(n_requests)) > 1  # lookups vary lengths

    for n in (4, 16):
        gate = _Gate(sum(n_requests[1:4]), eps[0].episode_id,
                     {e.episode_id for e in eps[1:4]})
        monkeypatch.setattr(parallel, "EpisodeChannel", gate.channel(gate))
        fake = FakeModel(_reply_fn(eps), ids="payload")
        meta = _run(eps, cid, fake, tmp_path / f"par{n}", n)
        assert gate.opened_by_count is True  # episodes 1-3 finished before episode 0
        assert _outputs(tmp_path / f"par{n}") == seq  # byte for byte
        assert _stable(meta) == _stable(seq_meta)  # config hash included
        assert _canonical(fake.calls) == _canonical(seq_fake.calls)  # the same payloads
        assert meta["exit_reason"] == "COMPLETED" and meta["parallel"] == {
            "max_episodes_in_flight": n, "peak_episodes_in_flight": n,
            "episodes_started": len(eps), "episodes_not_started": 0, "stop_reason": None,
            "abandoned_episode_ids": [], "spend_reservation": None}
        assert not (tmp_path / f"par{n}" / "raw" / "persistgym" / "r" / "inflight").exists()
    assert seq_meta["parallel"] == {"max_episodes_in_flight": 1}


def test_run_batch_refuses_a_bad_parallel_and_leftover_inflight_files(small_eps, tmp_path):
    for bad in (0, 17, -1, True, 2.0):
        with pytest.raises(ValueError, match="parallel must be an integer from 1 to 16"):
            _run(small_eps[:2], "F-0", FakeModel(), tmp_path, bad)
    left = tmp_path / "raw" / "persistgym" / "r" / "inflight"
    left.mkdir(parents=True)
    (left / "000003.jsonl").write_text("{}\n", encoding="utf-8")
    fake = FakeModel()
    with pytest.raises(ValueError, match="left by an earlier parallel run"):
        _run(small_eps[:2], "F-0", fake, tmp_path, 4)
    assert fake.calls == [] and not (tmp_path / "results").exists()


# --- spend reservations ----------------------------------------------------------------------

class _Budgeted:
    """The paid transport's spend rule around the fake model, safe across threads: spend is
    priced and measured as the paid transport does (`UsageLedger`, `spend_usd`), and a call
    is refused (`BudgetExceeded`, the episode's COST_CAP) once the spend recorded so far has
    reached the planned spend. `dearer_after` calls, every response's output tokens are
    multiplied by `factor`."""

    paid = False

    def __init__(self, fake: FakeModel, planned_usd: float, *, dearer_after: int | None = None,
                 factor: int = 1):
        self.fake, self.planned_usd = fake, planned_usd
        self.dearer_after, self.factor = dearer_after, factor
        self.ledger = UsageLedger("gpt-6-luna")
        self.lock = threading.Lock()
        self.refused = 0
        self.max_call_usd = 0.0

    @property
    def spent_usd(self) -> float:
        with self.lock:
            return spend_usd(self.ledger.cost_usd_list, self.ledger.cost_usd_billed_est)

    def send(self, payload: dict) -> dict:
        with self.lock:
            if spend_usd(self.ledger.cost_usd_list,
                         self.ledger.cost_usd_billed_est) >= self.planned_usd:
                self.refused += 1
                raise BudgetExceeded("run spend reached the planned spend")
            k = self.ledger.n_calls + self.refused
        response = copy.deepcopy(self.fake.send(payload))
        if self.dearer_after is not None and k >= self.dearer_after:
            response["usage"]["output_tokens"] *= self.factor
        with self.lock:
            _, billed = self.ledger.add(response)
            self.max_call_usd = max(self.max_call_usd, billed)
        return response


def _episode_spend(eps, cid) -> list[float]:
    """Each episode's spend when played alone (the fake is a function of the payload)."""
    out = []
    for ep in eps:
        t = _Budgeted(FakeModel(ids="payload"), planned_usd=1e9)
        runner.run_episode(ep, CELLS[cid], CFG, t)
        out.append(t.spent_usd)
    return out


def test_reservations_never_start_an_episode_the_planned_spend_cannot_hold(small_eps, tmp_path):
    """PREREG §4.6: before each start, spent + reserved + estimate <= planned spend; the
    first episode plays alone until one finishes; the run stops starting episodes, in the
    run's order, once the next does not fit, and never reaches the transport's own stop."""
    eps = small_eps
    spends = _episode_spend(eps, "F-r")
    planned = 12 * max(spends)  # room for about half of the 24 episodes
    t = _Budgeted(FakeModel(ids="payload"), planned)
    meta = _run(eps, "F-r", t, tmp_path, 4)
    lines = _lines(tmp_path)
    assert meta["exit_reason"] == "SPEND_RESERVATION"
    assert t.refused == 0 and t.spent_usd <= planned  # the transport's stop never fired
    assert [x["episode_id"] for x in lines] == [e.episode_id for e in eps[:len(lines)]]
    assert {x["exit_reason"] for x in lines} == {"DONE"} and 6 <= len(lines) < len(eps)
    log = [json.loads(x) for x in (tmp_path / "raw" / "persistgym" / "r" /
                                   runner.RESERVATIONS_LOG).read_text(encoding="utf-8")
           .splitlines()]
    assert [x["episode_index"] for x in log] == list(range(len(lines)))
    for x in log:
        assert x["spent_usd"] + x["reserved_usd"] + x["estimate_usd"] <= planned * (1 + 1e-12)
    # the first episode reserved all the planned spend and played alone
    assert log[0]["estimate_usd"] == pytest.approx(planned) and log[0]["in_flight"] == 0
    assert log[1]["spent_usd"] == pytest.approx(spends[0]) and log[1]["in_flight"] == 0
    # later estimates are twice the largest finished episode's spend
    assert log[1]["estimate_usd"] == pytest.approx(2 * spends[0])
    assert max(x["in_flight"] for x in log) == 3  # 4 at once
    info = meta["parallel"]
    assert info["peak_episodes_in_flight"] == 4 and info["stop_reason"] == "SPEND_RESERVATION"
    assert info["episodes_not_started"] == len(eps) - len(lines)
    res = info["spend_reservation"]
    assert res["planned_usd"] == planned and res["episodes_started"] == len(lines)
    assert res["estimate_factor"] == parallel.ESTIMATE_FACTOR == 2.0
    assert res["last_estimate_usd"] == pytest.approx(log[-1]["estimate_usd"])

    # sequential play under the same planned spend has no reservations: it runs into the
    # transport's stop and ends above its planned spend (by its last call)
    seq = _Budgeted(FakeModel(ids="payload"), planned)
    meta = _run(eps, "F-r", seq, tmp_path / "seq", 1)
    assert meta["exit_reason"] == "COST_CAP" and seq.refused == 1 and seq.spent_usd > planned


def test_a_blinded_run_keeps_its_spend_estimates_in_raw(small_eps, tmp_path):
    """PREREG §11: a pilot's committed meta.json has no per-episode spend estimate, and none
    of the call-gate waits and peaks in flight that the estimates and the per-call bounds
    decide (blinding.blinded_parallel); the whole `parallel` block is in the raw folder,
    next to the reservation log. A run that is not blinded commits the whole block."""
    eps = small_eps[:8]
    planned = 100 * max(_episode_spend(eps, "F-r"))
    pilot, main = "persistgym_pilot", "persistgym"
    for experiment in (pilot, main):
        root = tmp_path / experiment
        meta = _run(eps, "F-r", _Budgeted(FakeModel(ids="payload"), planned), root, 4,
                    experiment=experiment)
        assert meta["exit_reason"] == "COMPLETED"
        text = (root / "results" / experiment / "r" / "meta.json").read_text(encoding="utf-8")
        assert json.loads(text) == meta
        raw = root / "raw" / experiment / "r"
        log = [json.loads(x) for x in (raw / runner.RESERVATIONS_LOG).read_text(
            encoding="utf-8").splitlines()]
        res = meta["parallel"]["spend_reservation"]
        if experiment == main:
            assert res["last_estimate_usd"] == pytest.approx(log[-1]["estimate_usd"])
            assert meta["parallel"]["peak_episodes_in_flight"] == 4
            assert not (raw / runner.PARALLEL_INFO).exists() and "blinding" not in meta
            continue
        for word in ("estimate_usd", "reserved_usd", "spent_usd", "peak_", "calls_waited"):
            assert word not in text, word
        assert res["planned_usd"] == planned and res["estimate_factor"] == 2.0
        assert res["call_gate"]["calls"] == sum(x["n_requests"] for x in _lines(root, pilot))
        full = json.loads((raw / runner.PARALLEL_INFO).read_text(encoding="utf-8"))
        assert full["spend_reservation"]["last_estimate_usd"] == pytest.approx(
            log[-1]["estimate_usd"]) and log[-1]["estimate_usd"] < planned
        assert full["peak_episodes_in_flight"] == 4
        assert {"calls_waited", "peak_calls_in_flight"} <= set(
            full["spend_reservation"]["call_gate"])
        assert meta["parallel"] == blinding.blinded_parallel(full)
        assert meta["blinding"]["parallel_path"] == (raw / runner.PARALLEL_INFO).as_posix()
    # the pilot's raw block has every field the other run commits
    whole = json.loads((tmp_path / main / "results" / main / "r" / "meta.json")
                       .read_text(encoding="utf-8"))["parallel"]
    assert list(full) == list(whole)
    assert list(full["spend_reservation"]) == list(whole["spend_reservation"])
    assert (list(full["spend_reservation"]["call_gate"])
            == list(whole["spend_reservation"]["call_gate"]))


def test_a_run_whose_first_episode_does_not_finish_keeps_reserving_all_it_has(small_eps,
                                                                            tmp_path):
    """Only an episode that finished (DONE) gives an estimate: after an excluded one, the
    next episode again reserves all the planned spend leaves, so they play one at a time."""
    eps = small_eps[:4]

    def echo(payload, k):  # the first request of the run is mismatched (episode 0 alone)
        return "current_turn" if k == 0 else payload["reasoning"]["context"]
    t = _Budgeted(FakeModel(ids="payload", echo_context=echo), planned_usd=1.0)
    meta = _run(eps, "F-r", t, tmp_path, 4)
    lines = _lines(tmp_path)
    assert [x["exit_reason"] for x in lines] == ["REASONING_CONTEXT_MISMATCH"] + ["DONE"] * 3
    log = [json.loads(x) for x in (tmp_path / "raw" / "persistgym" / "r" /
                                   runner.RESERVATIONS_LOG).read_text(encoding="utf-8")
           .splitlines()]
    assert log[1]["estimate_usd"] == pytest.approx(1.0 - log[1]["spent_usd"])
    assert log[1]["in_flight"] == 0 and log[2]["in_flight"] == 0
    assert meta["exit_reason"] == "COMPLETED"


def test_the_transports_stop_is_the_backstop_when_estimates_run_short(small_eps, tmp_path):
    """Episodes after the first cost far more than it did: the reservation under-estimates,
    the transport's stop fires (COST_CAP) and stops the run, every other episode in flight
    makes no further call (RUN_STOPPED), and, with the per-call gate, the spend passes the
    planned spend by at most one call, as in sequential play."""
    eps = small_eps
    first = _episode_spend(eps[:1], "F-r")[0]
    planned = 8 * first
    t = _Budgeted(FakeModel(ids="payload"), planned, dearer_after=eps[0].n_steps, factor=200)
    meta = _run(eps, "F-r", t, tmp_path, 4)
    lines = _lines(tmp_path)
    assert meta["exit_reason"] == "COST_CAP" and t.refused >= 1
    assert lines[0]["exit_reason"] == "DONE"
    reasons = Counter(x["exit_reason"] for x in lines[1:])
    assert reasons["COST_CAP"] >= 1 and set(reasons) <= {"COST_CAP", "RUN_STOPPED", "DONE"}
    stopped = [x for x in lines if x["exit_reason"] == "RUN_STOPPED"]
    assert all("the run stopped (COST_CAP)" in x["error"] for x in stopped)
    assert t.spent_usd > planned and t.spent_usd - planned <= t.max_call_usd
    assert [x["episode_id"] for x in lines] == [e.episode_id for e in eps[:len(lines)]]


class _SlowFake(FakeModel):
    """Each call takes a moment, so that the calls of the episodes in flight overlap."""

    def send(self, payload):
        time.sleep(0.01)
        return super().send(payload)


@pytest.mark.parametrize("n", [4, 16])
def test_overlapping_calls_never_take_the_run_past_its_planned_spend(small_eps, tmp_path,
                                                                     n):
    """PREREG §4.6 ("it never exceeds its planned spend"): with up to 16 episodes in flight
    whose calls overlap, and episodes far dearer than their reservations, the per-call gate
    keeps the run within one call of its planned spend, as in sequential play. Without it
    the calls in flight when the transport's stop fires all complete, and this run ends
    several calls over (about 3 at 4 in flight and 12 at 16 in one trial). The gate lets
    calls overlap while there is room."""
    eps = small_eps
    first = _episode_spend(eps[:1], "F-r")[0]
    planned = 30 * first
    t = _Budgeted(_SlowFake(ids="payload"), planned, dearer_after=eps[0].n_steps, factor=200)
    meta = _run(eps, "F-r", t, tmp_path, n)
    assert meta["exit_reason"] == "COST_CAP" and t.refused >= 1
    assert planned < t.spent_usd <= planned + t.max_call_usd
    gate = meta["parallel"]["spend_reservation"]["call_gate"]
    assert gate["peak_calls_in_flight"] > 1 and gate["calls_waited"] >= 1
    assert gate["calls"] == t.ledger.n_calls + t.refused
    lines = _lines(tmp_path)
    assert [x["episode_id"] for x in lines] == [e.episode_id for e in eps[:len(lines)]]


def _gate(planned: float, spent: list[float]) -> parallel.CallGate:
    return parallel.CallGate(planned, lambda: spent[0], "gpt-6-luna", parallel.RunStop())


def _capped(cap=32_000, text="x") -> dict:
    return {"model": "gpt-6-luna", "max_output_tokens": cap,
            "input": [{"role": "user", "content": [{"type": "input_text", "text": text}]}]}


def test_call_gate_bound_is_the_output_cap_plus_a_token_per_input_byte():
    g = _gate(1.0, [0.0])
    p = _capped(text="é" * 10)
    n_bytes = len(json.dumps(p, ensure_ascii=False).encode("utf-8"))
    assert g.bound_usd(p) == pytest.approx((32_000 * 0.50 + n_bytes * 0.10 * 1.25) / 1e6)
    for cap in (None, 0, -1, True, 1.5):
        assert g.bound_usd({**p, "max_output_tokens": cap}) == float("inf")


def test_call_gate_lets_a_call_overlap_only_within_the_planned_spend():
    spent = [0.0]
    one = _gate(1.0, spent).bound_usd(_capped())  # about $0.016
    g = _gate(2.7 * one, spent)
    a = g.enter(_capped())  # alone: always (the transport's stop decides)
    b = g.enter(_capped())  # 2 bounds fit in 2.7
    spent[0] = 0.6 * one  # a call recorded since: 0.6 + 2 + 1 > 2.7, the next one waits
    entered = threading.Event()

    def third():
        g.leave(g.enter(_capped()))
        entered.set()
    th = threading.Thread(target=third)
    th.start()
    assert not entered.wait(0.3)
    g.leave(a)  # 0.6 + 1 + 1 <= 2.7
    assert entered.wait(WAIT_S)
    th.join(WAIT_S)
    g.leave(b)
    assert g.enter({**_capped(), "max_output_tokens": None}) is not None  # alone, unbounded
    assert g.info()["calls"] == 4 and g.info()["calls_waited"] == 1
    assert g.info()["peak_calls_in_flight"] == 2


def test_a_call_waiting_at_the_gate_stops_with_the_run():
    g = _gate(0.0, [0.0])
    g.enter(_capped())
    raised = []

    def waiter():
        try:
            g.enter(_capped())
        except parallel.RunStopped as e:
            raised.append(str(e))
    th = threading.Thread(target=waiter)
    th.start()
    g.stop.set("COST_CAP")
    th.join(WAIT_S)
    assert not th.is_alive() and raised and "the run stopped (COST_CAP)" in raised[0]
    assert g.info()["calls"] == 1


# --- the stop rules with episodes in flight ----------------------------------------------------

def _stop_gate(monkeypatch) -> threading.Event:
    """An event set when the run's stop is set."""
    stopped = threading.Event()

    class Stop(parallel.RunStop):
        def set(self, reason):
            super().set(reason)
            stopped.set()
    monkeypatch.setattr(parallel, "RunStop", Stop)
    return stopped


def _scripted(monkeypatch, failing: set[str], how: str, release: threading.Event, *,
              entered: threading.Semaphore | None = None, fail_after_waiting: int = 0):
    """Channels where every episode not in `failing` makes a slow second call: it is sent,
    then returns only once `release` is set (`entered` is released as it starts waiting).
    The episodes in `failing` fail: `how` = "mismatch" (their first response echoes a
    reasoning.context that does not match) or "api_error" (their first call raises an API
    error after it was sent), each only once `fail_after_waiting` other episodes are waiting
    in their second call; or "boom" (their second call raises an exception the runner does
    not handle)."""
    calls: Counter = Counter()
    lock = threading.Lock()
    waiting = Counter()
    ready = threading.Event()
    if not fail_after_waiting:
        ready.set()

    class Scripted(parallel.EpisodeChannel):
        def send(self, payload):
            with lock:
                calls[self.episode_id] += 1
                k = calls[self.episode_id]
            if self.episode_id in failing and how == "boom" and k == 2:
                raise RuntimeError("boom")
            response = super().send(payload)
            if self.episode_id in failing and how in ("mismatch", "api_error"):
                assert ready.wait(WAIT_S)
                if how == "api_error":
                    req = httpx.Request("POST", "https://example.invalid/v1/responses")
                    raise openai.APIConnectionError(request=req)
                response = copy.deepcopy(response)
                response["reasoning"]["context"] = "current_turn"
            elif self.episode_id not in failing and k == 2:
                with lock:
                    waiting["n"] += 1
                    if waiting["n"] >= fail_after_waiting:
                        ready.set()
                if entered is not None:
                    entered.release()
                assert release.wait(WAIT_S)
            return response
    monkeypatch.setattr(parallel, "EpisodeChannel", Scripted)
    return calls


@pytest.mark.parametrize("how, reason, ending", [
    ("mismatch", "ABORTED_CONTEXT_MISMATCH", "REASONING_CONTEXT_MISMATCH"),
    ("api_error", "ABORTED_API_ERRORS", "API_ERROR")])
def test_the_abort_rules_stop_the_episodes_in_flight(small_eps, tmp_path, monkeypatch, how,
                                                     reason, ending):
    """CLAUDE.md, PREREG §13: the run stops after 2 excluded (echo-mismatched) episodes, and
    after 2 API errors. With episodes in flight, each makes no call after the one it had in
    flight when the run stopped, and the run starts no more."""
    eps = small_eps[:8]
    stopped = _stop_gate(monkeypatch)
    # episodes 0 and 1 fail once episodes 2 and 3 are waiting for their second call
    _scripted(monkeypatch, {eps[0].episode_id, eps[1].episode_id}, how, stopped,
              fail_after_waiting=2)
    fake = FakeModel(ids="payload")
    meta = _run(eps, "F-r", fake, tmp_path, 4)
    lines = _lines(tmp_path)
    assert meta["exit_reason"] == reason and meta["parallel"]["stop_reason"] == reason
    assert [x["episode_id"] for x in lines] == [e.episode_id for e in eps[:len(lines)]]
    assert [x["exit_reason"] for x in lines[:2]] == [ending, ending]
    # an API error's call returned nothing, so it is neither counted nor in the transcript
    assert [x["n_requests"] for x in lines[:2]] == [int(how == "mismatch")] * 2
    assert [x["excluded"] for x in lines[:2]] == [how == "mismatch"] * 2
    # episodes 2 and 3 stopped after the call they had in flight; an episode started
    # between the two failures (at most 2: never more than 4 in flight) stopped too
    rest = lines[2:]
    assert 2 <= len(rest) <= 4 and len(lines) < len(eps)
    assert [x["n_requests"] for x in rest[:2]] == [2, 2]
    for x in rest:
        assert x["exit_reason"] == "RUN_STOPPED" and x["n_requests"] <= 2 and not x["excluded"]
        assert f"the run stopped ({reason})" in x["error"]
    assert len(fake.calls) == 2 + sum(x["n_requests"] for x in rest)
    assert meta["parallel"]["episodes_not_started"] == len(eps) - len(lines)
    # the transcript holds every call, episode by episode in the run's order
    order = [e["episode_id"] for e in _events(tmp_path)]
    assert order == [x["episode_id"] for x in lines for _ in range(x["n_requests"])]


def test_an_error_in_an_episode_stops_the_run_and_is_raised(small_eps, tmp_path, monkeypatch):
    """An exception the runner does not handle (a bug) stops the run as in sequential play,
    where it propagates: the episodes in flight stop after their call in flight, everything
    finished is written in the run's order, and the exception is raised."""
    eps = small_eps[:8]
    stopped = _stop_gate(monkeypatch)
    _scripted(monkeypatch, {eps[1].episode_id}, "boom", stopped)
    with pytest.raises(RuntimeError, match="boom"):
        _run(eps, "F-r", FakeModel(ids="payload"), tmp_path, 4)
    meta = json.loads((tmp_path / "results" / "persistgym" / "r" / "meta.json")
                      .read_text(encoding="utf-8"))
    assert meta["exit_reason"] == "ERROR:RuntimeError"
    assert meta["parallel"]["stop_reason"] == f"ERROR:RuntimeError in episode {eps[1].episode_id}"
    lines = _lines(tmp_path)
    ids = [x["episode_id"] for x in lines]
    assert eps[1].episode_id not in ids and ids == sorted(ids, key=[e.episode_id
                                                                    for e in eps].index)
    assert all(x["exit_reason"] == "RUN_STOPPED" for x in lines)
    # episode 1's one call is in the transcript, in its place
    order = [e["episode_id"] for e in _events(tmp_path)]
    assert order == sorted(order, key=[e.episode_id for e in eps].index)
    assert order.count(eps[1].episode_id) == 1


def _interrupt_once_all_wait(monkeypatch, entered: threading.Semaphore, n: int, times: int):
    """The main thread's wait for a finished episode raises KeyboardInterrupt (Ctrl+C) the
    first `times` times it is called with a timeout, the first once `n` episodes are waiting
    in their second call."""
    real = parallel._Pool.next_done
    raised = []

    def next_done(self, timeout):
        if timeout > 0 and len(raised) < times:
            if not raised:
                for _ in range(n):
                    assert entered.acquire(timeout=WAIT_S)
            raised.append(1)
            raise KeyboardInterrupt
        return real(self, timeout)
    monkeypatch.setattr(parallel._Pool, "next_done", next_done)


def test_ctrl_c_stops_the_run_after_the_calls_in_flight(small_eps, tmp_path, monkeypatch,
                                                        capsys):
    """The first Ctrl+C stops the run and waits for the call each episode has in flight, so
    that it is recorded; the episodes end RUN_STOPPED, everything is written in order and the
    KeyboardInterrupt is raised."""
    eps = small_eps[:8]
    stopped = _stop_gate(monkeypatch)
    entered = threading.Semaphore(0)
    _scripted(monkeypatch, set(), "none", stopped, entered=entered)
    _interrupt_once_all_wait(monkeypatch, entered, 4, times=1)
    with pytest.raises(KeyboardInterrupt):
        _run(eps, "F-r", FakeModel(ids="payload"), tmp_path, 4)
    assert "waiting for the call each of the 4 episodes in flight" in capsys.readouterr().err
    meta = json.loads((tmp_path / "results" / "persistgym" / "r" / "meta.json")
                      .read_text(encoding="utf-8"))
    assert meta["exit_reason"] == "ERROR:KeyboardInterrupt"
    assert meta["parallel"]["stop_reason"] == "interrupted (Ctrl+C)"
    assert meta["parallel"]["abandoned_episode_ids"] == []
    lines = _lines(tmp_path)
    assert [x["episode_id"] for x in lines] == [e.episode_id for e in eps[:4]]
    assert all(x["exit_reason"] == "RUN_STOPPED" and x["n_requests"] == 2 for x in lines)
    assert len(_events(tmp_path)) == 8
    assert not (tmp_path / "raw" / "persistgym" / "r" / "inflight").exists()


def test_a_second_ctrl_c_abandons_the_episodes_in_flight(small_eps, tmp_path, monkeypatch):
    """A second Ctrl+C stops the wait: the episodes in flight are abandoned, listed in
    meta.json, and their transcripts stay under inflight/ (for a paid run the transport then
    keeps the paid-run lock: test_paid_guard)."""
    eps = small_eps[:8]
    release = threading.Event()
    entered = threading.Semaphore(0)
    _scripted(monkeypatch, set(), "none", release, entered=entered)
    _interrupt_once_all_wait(monkeypatch, entered, 4, times=2)
    try:
        with pytest.raises(KeyboardInterrupt):
            _run(eps, "F-r", FakeModel(ids="payload"), tmp_path, 4)
        meta = json.loads((tmp_path / "results" / "persistgym" / "r" / "meta.json")
                          .read_text(encoding="utf-8"))
        info = meta["parallel"]
        assert info["abandoned_episode_ids"] == [e.episode_id for e in eps[:4]]
        inflight = tmp_path / "raw" / "persistgym" / "r" / "inflight"
        assert info["abandoned_transcripts"] == inflight.as_posix()
        assert sorted(p.name for p in inflight.iterdir()) == [f"{i:06d}.jsonl"
                                                              for i in range(4)]
        assert _outputs(tmp_path)["episodes.jsonl"] == b"" and _events(tmp_path) == []
        assert meta["n_episodes_run"] == 0
    finally:
        release.set()  # let the abandoned (daemon) workers return


def test_fake_model_payload_ids_do_not_depend_on_call_order():
    payloads = [{"model": "gpt-6-luna", "input": [{"role": "user", "content": [
        {"type": "input_text", "text": f"obs {i}"}]}], "reasoning": {"context": "all_turns"}}
        for i in range(3)]
    a, b = FakeModel(ids="payload"), FakeModel(ids="payload")
    first = [a.send(p) for p in payloads]
    second = [b.send(p) for p in reversed(payloads)][::-1]
    assert first == second and len({r["id"] for r in first}) == 3
    assert FakeModel().send(payloads[0])["id"] == "resp_t0"  # the default numbers calls
    with pytest.raises(ValueError, match="ids must be"):
        FakeModel(ids="random")
