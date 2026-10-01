"""Per-episode dependency graph: which observation reveals which component, which components
determine the target fact, and which action the fact determines.

"Needed" and "live" are read from this graph, which the generator builds from the episode
script. They never come from agent trajectories (PLAN §4).

Node ids:
  obs:<t>     the scheduled observation at step t
  act:<t>     the action expected at step t
  comp:<id>   a revealed component (fact, clue0..clue2, rule) or distractor (dist0, dist1)
  fact        the target fact (k=1)
  env:lookup  the lookup action (recoverable cells only)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DependencyGraph:
    nodes: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)
    need_step: int = -1
    live: dict[str, list[int]] = field(default_factory=dict)
    """Node id -> [first step it is live, last step it is live] (inclusive)."""

    # ------------------------------------------------------------------
    def needed_step(self, node: str = "fact") -> int | None:
        """The step at which `node` determines the only correct action."""
        if node == "fact":
            return self.need_step
        reachable = self._descendants(node)
        return self.need_step if "fact" in reachable or node == "fact" else None

    def required_components(self) -> list[str]:
        """Component nodes the fact depends on (the 'fact or all its clues' of S)."""
        return [e["src"] for e in self.edges if e["dst"] == "fact" and e["rel"] in
                ("is", "derives")]

    def live_at(self, step: int) -> list[str]:
        """Nodes that must be carried at `step`: revealed at or before it and needed later
        or at it."""
        return [n for n, (a, b) in self.live.items() if a <= step <= b]

    def parents(self, node: str) -> list[str]:
        return [e["src"] for e in self.edges if e["dst"] == node]

    def _descendants(self, node: str) -> set[str]:
        out, frontier = set(), [node]
        while frontier:
            cur = frontier.pop()
            for e in self.edges:
                if e["src"] == cur and e["dst"] not in out:
                    out.add(e["dst"])
                    frontier.append(e["dst"])
        return out

    def to_dict(self) -> dict:
        return {"nodes": self.nodes, "edges": self.edges, "need_step": self.need_step,
                "live": self.live}

    @classmethod
    def from_dict(cls, d: dict) -> DependencyGraph:
        return cls(nodes=list(d["nodes"]), edges=list(d["edges"]), need_step=d["need_step"],
                   live={k: list(v) for k, v in d["live"].items()})


def build_graph(n_steps: int, need_step: int, components: list[dict], fact_kind: str,
                recoverable: bool, rule_in_system_prompt: bool = False,
                distractors: list[dict] = ()) -> DependencyGraph:
    """Build the graph from the episode script.

    `components`: dicts with comp_id, role and step (step None = always visible, e.g. a rule
    in the system prompt; or not shown at all in the withheld control, role 'null').
    `distractors`: dicts with comp_id and step. A distractor is revealed (and re-shown by
    lookup) but has no edge to the fact, so it is never needed and never live.
    """
    g = DependencyGraph(need_step=need_step)
    for t in range(n_steps):
        g.nodes.append({"id": f"obs:{t}", "kind": "observation", "step": t})
        g.nodes.append({"id": f"act:{t}", "kind": "action", "step": t})
    g.nodes.append({"id": "fact", "kind": "fact", "step": None})
    reveal_steps = []
    for c in components:
        cid = f"comp:{c['comp_id']}"
        g.nodes.append({"id": cid, "kind": "component", "role": c["role"], "step": c["step"]})
        if c["step"] is not None:
            g.edges.append({"src": f"obs:{c['step']}", "dst": cid, "rel": "reveals"})
            reveal_steps.append(c["step"])
        elif rule_in_system_prompt and c["role"] == "rule":
            g.edges.append({"src": "system_prompt", "dst": cid, "rel": "reveals"})
        g.edges.append({"src": cid, "dst": "fact",
                        "rel": "is" if fact_kind == "observed" else "derives"})
        if recoverable:
            g.edges.append({"src": "env:lookup", "dst": cid, "rel": "re-shows"})
        first = c["step"] if c["step"] is not None else 0
        g.live[cid] = [first, need_step]
    for d in distractors:
        did = f"comp:{d['comp_id']}"
        g.nodes.append({"id": did, "kind": "component", "role": "distractor", "step": d["step"]})
        g.edges.append({"src": f"obs:{d['step']}", "dst": did, "rel": "reveals"})
        if recoverable:
            g.edges.append({"src": "env:lookup", "dst": did, "rel": "re-shows"})
    if recoverable:
        g.nodes.append({"id": "env:lookup", "kind": "env_action", "step": None})
    if rule_in_system_prompt:
        g.nodes.append({"id": "system_prompt", "kind": "observation", "step": None})
    g.edges.append({"src": "fact", "dst": f"act:{need_step}", "rel": "determines"})
    g.edges.append({"src": f"obs:{need_step}", "dst": f"act:{need_step}", "rel": "offers_options"})
    for t in range(n_steps):
        if t != need_step:
            g.edges.append({"src": f"obs:{t}", "dst": f"act:{t}", "rel": "determines"})
    g.live["fact"] = [max(reveal_steps) if reveal_steps else need_step, need_step]
    return g
