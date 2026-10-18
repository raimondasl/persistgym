"""Parallel play of one run's episodes (PREREG §4.6; §0.3 line 15).

> PersistGym runs go one at a time, but a run may play up to 16 episodes in parallel. This
> changes no payload and no cost. The run reserves spend for the episodes in flight, so it
> never exceeds its planned spend. (PREREG §0.3, line 15, changed by the researcher on
> 2026-10-01)

`runner.run_batch(..., parallel=N)` with 2 <= N <= 16 (CLI `run --parallel N`) plays the
run's episodes with `ParallelPlay`; N = 1, the default, is the sequential loop, unchanged.

What parallel play keeps from sequential play:
* **Payloads, cell assignment and seeds.** Every episode has its own session and environment,
  as it does sequentially, and sends what it sends when played alone; nothing is shared
  between episodes but the transport. Episodes start in the run's order (template by
  template, `ALL_CELLS` order within a template; `harnesses.matrix`), so the episodes started
  are always a prefix of that order.
* **Output order.** episodes.jsonl and the raw transcript are written in the run's order, not
  in the order the episodes finish. While an episode plays, its transcript goes to its own
  file, `results/raw/<experiment>/<run_id>/inflight/<index>.jsonl` (gitignored, like the
  transcript, so pilot blinding holds); once it and every earlier episode have finished, its
  record is appended to episodes.jsonl and that file to the run's transcript. With the same
  responses the two files are byte for byte those of sequential play, apart from the
  wall-clock seconds of each call (`call_latency_s`); harnesses/tests/test_parallel.py checks
  this with the fake model.
* **The stop rules** (`runner._stop_reason`): COST_CAP, and the aborts after 2 excluded
  (echo-mismatched) episodes or 2 API errors, checked as each episode finishes, in the order
  they finish. When the run stops, for one of these or for an error or a Ctrl+C, no episode
  starts any more and every episode in flight makes no further call: its next call, or a
  call still waiting at the per-call gate (below), raises `RunStopped` and it ends
  `RUN_STOPPED`, and its record and transcript are written like any other. Only the call
  each one had in flight is made, so the run stops within one call per episode in flight.

**Spend reservations** (`SpendPlan`; only for a transport with a planned spend, i.e. the paid
one). Before an episode starts, the run reserves a conservative estimate of its spend, and
it does not start the episode unless

    spent + reserved + estimate <= planned spend

where spent is the run's spend so far, measured like block spend (the transport's
`spent_usd`: the billed estimate), and reserved is what the episodes in flight have reserved
and not yet spent. The estimate is twice the largest spend of a finished episode of this
run, once one has finished `DONE` (a whole episode); before that, it is all that the planned
spend leaves, so episodes play one at a time until one has finished `DONE`. If the next
episode does not fit, the run waits for an episode in flight to finish and checks again;
with none in flight, it starts no more episodes and ends `SPEND_RESERVATION`. Every start is logged (`SpendPlan.log`, written by the
runner to `spend_reservations.jsonl` next to the transcript).

**Per-call gate** (`CallGate`; with the spend plan). A reservation is an estimate, and an
episode can spend more than it reserved. The transport's own stop, unchanged, refuses a call
once the run's spend as recorded so far has reached the planned spend (`BudgetExceeded`, the
episode's `COST_CAP`), but the calls already sent when it fires still complete: on its own it
would let a parallel run end above its planned spend by up to one call per episode in flight.
So each call of a parallel paid run first passes the gate. With no other call in flight it
goes ahead (the transport then applies the rule of sequential play); with others in flight
it goes only if

    spent + the most the calls in flight can cost + the most this call can cost
        <= planned spend

and otherwise waits for a call in flight to return (or for the run to stop). The most a call
can cost is its `max_output_tokens` (D13: 32,000 on every request; `max_tokens` on the
Messages wire) at the output price plus one input token per byte of its JSON body at the
cache-write price, at the standard tier's list prices, on the dearest card where the price
depends on prompt size (claude-haiku-5-5's card above 100,000 tokens) (`CallGate.bound_usd`);
a request without a cap counts as unbounded, so it goes only alone. So the calls that
overlap can never take the run past its planned spend, and a parallel run ends above it by at
most the one call that went alone, as a sequential run can.
This rests on one assumption: that a request's input tokens are no more than the bytes of its
JSON body, which holds for text (an o200k_base token is at least one byte), is assumed for
Claude's tokenizer on the Messages wire (`harnesses count-tokens` measures its counts against
o200k_base) and is assumed for replayed reasoning items, whose `encrypted_content` carries
those tokens. The gate waits only
when the planned spend has less room left than the bounds of the calls that would overlap, so
it changes the timing of calls near the end of a run, never a payload.

**Ctrl+C** (in the main thread; the episodes play in daemon worker threads). The first stops
the run and waits for the calls in flight to return, so that they are recorded; the episodes
then end `RUN_STOPPED` and everything is written as above. A second Ctrl+C stops the wait:
the episodes still in flight are abandoned (`ParallelPlay.abandoned`), their transcript files
stay under `inflight/`, and the paid transport, finalized with calls in flight, keeps the
paid-run lock with the reason (`PaidTransport.finalize`), since those calls' usage
is not in costs.csv.
"""

from __future__ import annotations

import itertools
import json
import math
import queue
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from common.costs import spend_usd
from harnesses.pricing import CACHE_WRITE_MULTIPLIER, UsageLedger, price_for
from harnesses.wire import wire_for

MAX_PARALLEL = 16
"""PREREG §4.6, §0.3 line 15: a run plays at most 16 episodes at once."""
ESTIMATE_FACTOR = 2.0
"""An episode's spend estimate is this times the largest spend of a finished episode of the
run. Episodes differ in length (21 to 27 steps over the first 120 main-split templates, plus
any lookup turns), and a full-history episode's input grows with about the square of its
length, so a long episode can cost about twice a short one; the largest grows as longer
episodes finish, and the transport's stop catches what an estimate still misses."""
POLL_S = 0.5
"""How long the main thread waits for a finished episode at a time, so that a Ctrl+C is
handled within this many seconds (a blocking wait cannot be interrupted on Windows)."""

RUN_STOPPED = "RUN_STOPPED"
"""Episode exit reason: the run stopped while this episode was in flight."""
SPEND_RESERVATION = "SPEND_RESERVATION"
"""Run exit reason: the next episode's spend estimate did not fit in what the planned spend
left, with no episode in flight."""


class RunStopped(RuntimeError):
    """Raised in place of an episode's next call once the run has stopped (parallel play):
    the episode ends `RUN_STOPPED` and makes no further call."""


def check_parallel(n: Any) -> int:
    """`n` must be an integer from 1 to `MAX_PARALLEL`."""
    if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= MAX_PARALLEL:
        raise ValueError(f"parallel must be an integer from 1 to {MAX_PARALLEL} "
                         f"(PREREG §4.6), got {n!r}")
    return n


class RunStop:
    """The run's stop signal. Once set, no episode starts and no episode makes another call.
    The first reason stays."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self.reason: str | None = None

    def set(self, reason: str) -> None:
        if not self._event.is_set():
            self.reason = reason
            self._event.set()

    def is_set(self) -> bool:
        return self._event.is_set()


def _stopped(stop: RunStop) -> RunStopped:
    return RunStopped(f"the run stopped ({stop.reason}) while this episode was in flight; it "
                      "made no further call")


class CallGate:
    """The per-call backstop of a parallel paid run (module docstring): a call goes ahead
    alone, or with other calls in flight only if the spend recorded so far plus the most
    every call in flight and this one can cost stays within the planned spend; otherwise it
    waits for a call to return. So the calls that overlap never take the run past its
    planned spend. Shared by the episodes' channels, safe across threads."""

    RULE = ("a call goes alone, or with others in flight only if spent + the most the calls "
            "in flight and this one can cost <= planned spend; the most a call can cost is "
            "its max_output_tokens at the output price plus one input token per byte of its "
            "JSON body at the cache-write price, at list prices")
    RULE_MESSAGES = ("a call goes alone, or with others in flight only if spent + the most the "
                     "calls in flight and this one can cost <= planned spend; the most a call "
                     "can cost is its max_tokens at the output price plus one input token per "
                     "byte of its JSON body at the cache-write price, at list prices on the "
                     "dearest card of a price that depends on prompt size (claude-haiku-5-5: "
                     "its card for prompts over 100,000 tokens)")
    """`RULE` on the Messages wire (`harnesses.wire.MessagesWire`), whose cap is `max_tokens`."""

    def __init__(self, planned_usd: float, spent: Callable[[], float], model: str,
                 stop: RunStop):
        self.planned_usd = float(planned_usd)
        self._spent = spent
        self.price = price_for(model)
        self.wire = wire_for(model)
        self.rule = self.RULE if self.wire.echoes_reasoning else self.RULE_MESSAGES
        self.stop = stop
        self._cond = threading.Condition()
        self._in_flight: dict[int, float] = {}  # ticket -> the most that call can cost
        self._tickets = itertools.count()
        self.calls = 0  # calls let through
        self.calls_waited = 0  # of those, the ones that had to wait
        self.peak_calls_in_flight = 0

    def bound_usd(self, payload: dict) -> float:
        """The most one call with this payload can cost, at list prices (no Flex discount):
        its output cap (`max_output_tokens`; `max_tokens` on the Messages wire) at the output
        price, plus one input token per byte of its JSON body at the cache-write price (more
        than the uncached and cached prices), on the dearest card of a price that depends on
        prompt size (`Price.worst_card`: claude-haiku-5-5's card above 100,000 tokens).
        Unbounded (inf) without a positive integer cap."""
        cap = self.wire.cap(payload)
        if isinstance(cap, bool) or not isinstance(cap, int) or cap <= 0:
            return math.inf
        n_bytes = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        inp, _, out = self.price.worst_card()
        return (n_bytes * inp * CACHE_WRITE_MULTIPLIER + cap * out) / 1e6

    def enter(self, payload: dict) -> int:
        """Wait until this call may go (or raise `RunStopped` once the run stops); returns
        the ticket to pass to `leave` once the call has returned or failed."""
        bound = self.bound_usd(payload)
        waited = False
        with self._cond:
            while True:
                if self.stop.is_set():
                    raise _stopped(self.stop)
                if not self._in_flight:
                    break  # alone: the transport's own stop decides, as in sequential play
                # A call leaves only after the transport recorded its spend, and none leaves
                # while this lock is held: a call is counted twice here, never not at all.
                if (float(self._spent()) + sum(self._in_flight.values()) + bound
                        <= self.planned_usd):
                    break
                waited = True
                self._cond.wait(POLL_S)  # woken when a call returns; polls the run's stop
            ticket = next(self._tickets)
            self._in_flight[ticket] = bound
            self.calls += 1
            self.calls_waited += waited
            self.peak_calls_in_flight = max(self.peak_calls_in_flight, len(self._in_flight))
            return ticket

    def leave(self, ticket: int) -> None:
        with self._cond:
            self._in_flight.pop(ticket, None)
            self._cond.notify_all()

    def info(self) -> dict:
        with self._cond:
            return {"rule": self.rule, "calls": self.calls, "calls_waited": self.calls_waited,
                    "peak_calls_in_flight": self.peak_calls_in_flight}


class EpisodeChannel:
    """What one episode of a parallel run sends through: the run's transport, behind the
    run's stop signal and, for a paid run, the run's `CallGate`. With a spend plan it also
    meters the episode's spend, priced as the paid transport prices it (`UsageLedger`) and
    measured like block spend (`spend_usd`)."""

    def __init__(self, transport: Any, stop: RunStop, ledger: UsageLedger | None = None, *,
                 episode_id: str = "", gate: CallGate | None = None):
        self.transport = transport
        self.episode_id = episode_id
        self.paid = bool(getattr(transport, "paid", False))
        self.stop = stop
        self.ledger = ledger
        self.gate = gate
        self._lock = threading.Lock()

    def send(self, payload: dict) -> dict:
        if self.stop.is_set():
            raise _stopped(self.stop)
        if self.gate is None:
            response = self.transport.send(payload)
        else:
            ticket = self.gate.enter(payload)
            try:
                response = self.transport.send(payload)
            finally:
                self.gate.leave(ticket)  # after the transport recorded the call's spend
        if self.ledger is not None:
            with self._lock:
                self.ledger.add(response)
        return response

    @property
    def spent_usd(self) -> float:
        if self.ledger is None:
            return 0.0
        with self._lock:
            return spend_usd(self.ledger.cost_usd_list, self.ledger.cost_usd_billed_est)


@dataclass
class _Flight:
    index: int
    episode: Any
    channel: EpisodeChannel
    estimate_usd: float | None  # reserved at its start; None without a spend plan
    # (record, exception) once it finished: one assignment, so that a Ctrl+C cannot leave a
    # flight half finished
    result: tuple | None = None
    submitted: bool = False  # handed to a worker
    emitted: bool = False

    @property
    def finished(self) -> bool:
        return self.result is not None

    @property
    def run(self) -> Any:
        return self.result[0] if self.result is not None else None

    @property
    def error(self) -> BaseException | None:
        return self.result[1] if self.result is not None else None


class SpendPlan:
    """Episode reservations against the run's planned spend (PREREG §4.6; module docstring).
    Used only from the main thread."""

    def __init__(self, planned_usd: float, spent: Callable[[], float]):
        self.planned_usd = float(planned_usd)
        self._spent = spent
        self.finished_spends: list[float] = []  # spend of each episode that finished
        self.whole_episode = False  # whether one of them finished DONE
        self.log: list[dict] = []  # one entry per episode started

    @classmethod
    def for_transport(cls, transport: Any) -> SpendPlan | None:
        """A plan for a transport with a planned spend and a `spent_usd` (the paid one);
        None for one without (the fake model)."""
        planned = getattr(transport, "planned_usd", None)
        if planned is None or not hasattr(transport, "spent_usd"):
            return None
        return cls(planned, lambda: transport.spent_usd)

    @property
    def estimate_rule(self) -> str:
        return (f"{ESTIMATE_FACTOR:g} x the largest spend of a finished episode of the run, "
                "once one has finished DONE; before that, all the planned spend leaves")

    def estimate(self, room: float) -> float:
        if self.whole_episode:
            return ESTIMATE_FACTOR * max(self.finished_spends)
        return max(room, 0.0)

    def admit(self, flight_index: int, episode_id: str,
              in_flight: list[_Flight]) -> float | None:
        """The estimate to reserve for the next episode if it fits, else None. The episodes
        in flight are read before the run's spend, so a call that returns in between is
        counted twice, never not at all."""
        reserved = sum(max(f.estimate_usd - f.channel.spent_usd, 0.0) for f in in_flight)
        spent = float(self._spent())
        room = self.planned_usd - spent
        estimate = self.estimate(room)
        if reserved + estimate > room:
            return None
        self.log.append({"episode_index": flight_index, "episode_id": episode_id,
                         "spent_usd": spent, "reserved_usd": reserved,
                         "estimate_usd": estimate, "planned_usd": self.planned_usd,
                         "in_flight": len(in_flight)})
        return estimate

    def finished(self, flight: _Flight) -> None:
        """Every finished episode's spend counts toward the largest, so an episode that
        stopped early can only raise the estimate; only one that finished DONE, a whole
        episode, ends the upper bound."""
        if flight.run is None:
            return
        self.finished_spends.append(flight.channel.spent_usd)
        if getattr(flight.run, "exit_reason", None) == "DONE":
            self.whole_episode = True

    def info(self) -> dict:
        return {"planned_usd": self.planned_usd, "estimate_rule": self.estimate_rule,
                "estimate_factor": ESTIMATE_FACTOR, "episodes_started": len(self.log),
                "episodes_measured": len(self.finished_spends),
                "whole_episode_measured": self.whole_episode,
                "last_estimate_usd": self.log[-1]["estimate_usd"] if self.log else None}


class _Pool:
    """N daemon worker threads, each running one episode at a time. Daemon threads, so that a
    Ctrl+C that abandons the episodes in flight does not wait for their calls to return."""

    def __init__(self, n: int):
        self._tasks: queue.SimpleQueue = queue.SimpleQueue()
        self._done: queue.SimpleQueue = queue.SimpleQueue()
        self._threads = [threading.Thread(target=self._work, name=f"persistgym-episode-{k}",
                                          daemon=True) for k in range(n)]
        for t in self._threads:
            t.start()

    def _work(self) -> None:
        while (task := self._tasks.get()) is not None:
            self._done.put(task())

    def submit(self, task: Callable[[], Any]) -> None:
        self._tasks.put(task)

    def next_done(self, timeout: float) -> Any:
        """The next finished task's result, or None if none finished within `timeout`."""
        try:
            return self._done.get(timeout=timeout) if timeout > 0 else self._done.get_nowait()
        except queue.Empty:
            return None

    def close(self) -> None:
        for _ in self._threads:
            self._tasks.put(None)


class ParallelPlay:
    """Play `episodes` with up to `parallel` of them at once (module docstring).

    * `play_one(index, episode, channel)` plays one episode through `channel` and returns its
      record (`runner.EpisodeRun`); it runs in a worker thread.
    * `stop_rule(finished, last)` is the run's stop rule (`runner._stop_reason`): the run's
      exit reason once it must stop, else None. `finished` holds the records of the episodes
      finished so far, in the order they finished, and `last` the one that just did.
    * `emit(index, record)` writes one episode's outputs (its episodes.jsonl line and its
      transcript); it is called in the run's order for every episode started, with record
      None for an episode that raised. It runs in the main thread.

    After `run()`, or after it raised, `runs` holds the records emitted, in the run's order,
    `exit_reason` the run's exit reason and `abandoned` the indices of the episodes still in
    flight when a second Ctrl+C stopped the wait for them."""

    def __init__(self, episodes: list, *, parallel: int, transport: Any, model: str,
                 play_one: Callable[[int, Any, EpisodeChannel], Any],
                 stop_rule: Callable[[list, Any], str | None],
                 emit: Callable[[int, Any], None]):
        self.episodes = episodes
        self.parallel = check_parallel(parallel)
        self.transport = transport
        self.model = model
        self.play_one = play_one
        self.stop_rule = stop_rule
        self.emit = emit
        self.stop = RunStop()
        self.plan = SpendPlan.for_transport(transport)
        self.gate = (CallGate(self.plan.planned_usd, lambda: transport.spent_usd, model,
                              self.stop) if self.plan is not None else None)
        self.flights: dict[int, _Flight] = {}
        self.finished_runs: list = []  # in the order they finished (the stop rule)
        self.runs: list = []  # emitted, in the run's order
        self.exit_reason = "COMPLETED"
        self.error: BaseException | None = None  # the first exception an episode raised
        self.abandoned: list[int] = []
        self.peak_in_flight = 0
        self._next_emit = 0

    # ------------------------------------------------------------------
    def _in_flight(self) -> list[_Flight]:
        return [f for f in self.flights.values() if f.submitted and not f.finished]

    def _task(self, flight: _Flight) -> Callable[[], tuple]:
        def task() -> tuple:
            try:
                return flight.index, self.play_one(flight.index, flight.episode,
                                                   flight.channel), None
            except BaseException as e:  # noqa: BLE001 - re-raised in the main thread
                return flight.index, None, e
        return task

    def _start_more(self, pool: _Pool) -> None:
        while not self.stop.is_set() and len(self.flights) < len(self.episodes):
            in_flight = self._in_flight()
            if len(in_flight) >= self.parallel:
                return
            index = len(self.flights)
            episode = self.episodes[index]
            estimate = None
            if self.plan is not None:
                estimate = self.plan.admit(index, getattr(episode, "episode_id", str(index)),
                                           in_flight)
                if estimate is None:
                    if not in_flight:  # it will never fit: stop here, in the run's order
                        self.exit_reason = SPEND_RESERVATION
                        self.stop.set(SPEND_RESERVATION)
                    return
            ledger = UsageLedger(self.model) if self.plan is not None else None
            channel = EpisodeChannel(self.transport, self.stop, ledger,
                                     episode_id=getattr(episode, "episode_id", str(index)),
                                     gate=self.gate)
            flight = _Flight(index, episode, channel, estimate)
            self.flights[index] = flight
            pool.submit(self._task(flight))
            flight.submitted = True
            self.peak_in_flight = max(self.peak_in_flight, len(in_flight) + 1)

    def _finish(self, result: tuple) -> None:
        index, run, error = result
        flight = self.flights[index]
        flight.result = (run, error)
        if error is not None:
            if self.error is None:
                self.error = error
            self.stop.set(f"ERROR:{type(error).__name__} in episode "
                          f"{getattr(flight.episode, 'episode_id', index)}")
            return
        self.finished_runs.append(run)
        if self.plan is not None:
            self.plan.finished(flight)
        reason = self.stop_rule(self.finished_runs, run)
        if reason and not self.stop.is_set():
            self.exit_reason = reason
            self.stop.set(reason)

    def _emit_ready(self, *, final: bool = False) -> None:
        """Emit, in the run's order, every finished episode whose predecessors are all
        emitted. `final`: also those after an abandoned one (whose outputs stay in
        inflight/)."""
        while self._next_emit < len(self.flights):
            flight = self.flights[self._next_emit]
            if not flight.finished:
                break
            self._emit(flight)
            self._next_emit += 1
        if final:
            for i in sorted(self.flights):
                flight = self.flights[i]
                if i >= self._next_emit and flight.finished:
                    self._emit(flight)

    def _emit(self, flight: _Flight) -> None:
        if flight.emitted:
            return
        flight.emitted = True
        self.emit(flight.index, flight.run)
        if flight.run is not None:
            self.runs.append(flight.run)

    def _wait_for_in_flight(self, pool: _Pool) -> None:
        while self._in_flight():
            result = pool.next_done(POLL_S)
            if result is not None:
                self._finish(result)

    # ------------------------------------------------------------------
    def run(self) -> None:
        pool = _Pool(min(self.parallel, max(len(self.episodes), 1)))
        try:
            try:
                self._start_more(pool)
                while self._in_flight():
                    result = pool.next_done(POLL_S)
                    while result is not None:
                        self._finish(result)
                        result = pool.next_done(0)
                    self._emit_ready()
                    self._start_more(pool)
            except BaseException as e:  # a Ctrl+C, or an error writing the outputs
                self.stop.set("interrupted (Ctrl+C)" if isinstance(e, KeyboardInterrupt)
                              else f"ERROR:{type(e).__name__}")
                n = len(self._in_flight())
                if n:
                    print(f"stopping the run: waiting for the call each of the {n} episodes "
                          "in flight has made to return, so that it is recorded. Ctrl+C "
                          "again stops waiting: those calls are then recorded nowhere, and "
                          "a paid run keeps its paid-run lock", file=sys.stderr, flush=True)
                try:
                    self._wait_for_in_flight(pool)
                except BaseException:
                    self.abandoned = sorted(f.index for f in self._in_flight())
                    raise
                finally:
                    self._emit_ready(final=True)
                raise
            self._emit_ready(final=True)
        finally:
            pool.close()
        if self.error is not None:
            raise self.error

    def info(self) -> dict:
        """For meta.json (`parallel`)."""
        return {"max_episodes_in_flight": self.parallel,
                "peak_episodes_in_flight": self.peak_in_flight,
                "episodes_started": len(self.flights),
                "episodes_not_started": len(self.episodes) - len(self.flights),
                "stop_reason": self.stop.reason,
                "abandoned_episode_ids": [getattr(self.flights[i].episode, "episode_id", i)
                                          for i in self.abandoned],
                "spend_reservation": ({**self.plan.info(), "call_gate": self.gate.info()}
                                      if self.plan is not None else None)}
