"""Semantic memory = a knowledge graph (NetworkX).

People and things become nodes; traits, preferences and relations become typed
edges carrying ``weight`` / ``count`` / ``last_seen`` so the self-evolution
module can strengthen or decay them over time. Persisted as JSON.
"""

from __future__ import annotations

import json
import threading
import time

import networkx as nx

from app.config import settings


class SemanticMemory:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.g = nx.MultiDiGraph()
        self._load()

    def _load(self) -> None:
        if settings.graph_path.exists():
            try:
                data = json.loads(settings.graph_path.read_text(encoding="utf-8"))
                self.g = nx.node_link_graph(data, multigraph=True, directed=True, edges="links")
            except Exception:
                self.g = nx.MultiDiGraph()

    def _persist(self) -> None:
        try:
            data = nx.node_link_data(self.g, edges="links")
            settings.graph_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    # ---------------------------------------------------------------- writes
    def add_person(self, name: str, aliases: list[str] | None = None) -> None:
        with self._lock:
            if self.g.has_node(name):
                self.g.nodes[name]["count"] = self.g.nodes[name].get("count", 0) + 1
            else:
                self.g.add_node(name, kind="person", count=1)
            if aliases:
                existing = set(self.g.nodes[name].get("aliases", []))
                existing.update(aliases)
                self.g.nodes[name]["aliases"] = sorted(existing)
            self.g.nodes[name]["last_seen"] = time.time()

    def _bump_edge(self, subj: str, obj: str, kind: str, label: str, gain: float) -> None:
        # find an existing edge of same kind+label
        if self.g.has_edge(subj, obj):
            for key, data in self.g[subj][obj].items():
                if data.get("kind") == kind and data.get("label") == label:
                    data["count"] = data.get("count", 0) + 1
                    data["weight"] = round(data.get("weight", 1.0) + gain, 4)
                    data["last_seen"] = time.time()
                    return
        self.g.add_edge(
            subj,
            obj,
            kind=kind,
            label=label,
            count=1,
            weight=1.0,
            last_seen=time.time(),
        )

    def add_trait(self, person: str, trait: str, gain: float = 0.3) -> None:
        with self._lock:
            self.add_person(person)
            node = f"trait:{trait}"
            if not self.g.has_node(node):
                self.g.add_node(node, kind="trait", label=trait)
            self._bump_edge(person, node, "trait", trait, gain)

    def add_preference(self, person: str, pref: str, gain: float = 0.3) -> None:
        with self._lock:
            self.add_person(person)
            node = f"pref:{pref}"
            if not self.g.has_node(node):
                self.g.add_node(node, kind="preference", label=pref)
            self._bump_edge(person, node, "preference", pref, gain)

    def add_relation(self, subject: str, relation: str, obj: str, gain: float = 0.3) -> None:
        with self._lock:
            self.add_person(subject)
            if not self.g.has_node(obj):
                self.g.add_node(obj, kind="entity", label=obj)
            self._bump_edge(subject, obj, "relation", relation, gain)

    # --- assistant (三叶虫) self-model ------------------------------------
    def add_self(self, name: str) -> None:
        """Create the assistant node (kind='assistant', not a tracked person)."""
        with self._lock:
            if not self.g.has_node(name):
                self.g.add_node(name, kind="assistant", label=name, count=1)
            self.g.nodes[name]["last_seen"] = time.time()

    def add_self_trait(self, name: str, trait: str, gain: float = 0.3) -> None:
        """Attach a trait edge to the assistant node (reuses shared trait nodes
        so 三叶虫 and people who share a trait become visibly connected)."""
        with self._lock:
            self.add_self(name)
            node = f"trait:{trait}"
            if not self.g.has_node(node):
                self.g.add_node(node, kind="trait", label=trait)
            self._bump_edge(name, node, "trait", trait, gain)

    def add_self_preference(self, name: str, pref: str, gain: float = 0.3) -> None:
        """Attach a preference edge to the assistant node."""
        with self._lock:
            self.add_self(name)
            node = f"pref:{pref}"
            if not self.g.has_node(node):
                self.g.add_node(node, kind="preference", label=pref)
            self._bump_edge(name, node, "preference", pref, gain)

    def add_self_relation(self, subject: str, relation: str, obj: str, gain: float = 0.3) -> None:
        """Explicitly add a relation edge from the assistant to a person.

        Bypasses the evolver's assistant filter; the target person node is
        created via the normal person path so it joins the social graph.
        """
        with self._lock:
            self.add_self(subject)
            if not self.g.has_node(obj):
                self.add_person(obj)
            self._bump_edge(subject, obj, "relation", relation, gain)

    def knows(self, name: str) -> list[str]:
        """People the given (assistant) node has an outgoing relation to."""
        if not self.g.has_node(name):
            return []
        out = []
        for _, tgt, data in self.g.out_edges(name, data=True):
            if data.get("kind") == "relation" and self.g.nodes[tgt].get("kind") == "person":
                out.append(tgt)
        return out

    def social_links(self, person: str) -> list[dict]:
        """Find people connected to ``person`` via a person-person relation,
        searching both edge directions. Used to surface mutual acquaintances."""
        person = self.resolve(person) or person
        if not self.g.has_node(person):
            return []
        links: dict[str, dict] = {}
        for _, tgt, data in self.g.out_edges(person, data=True):
            if data.get("kind") == "relation" and self.g.nodes[tgt].get("kind") == "person":
                links[tgt] = {"person": tgt, "relation": data.get("label", "认识"), "direction": "out"}
        for src, _, data in self.g.in_edges(person, data=True):
            if (
                data.get("kind") == "relation"
                and self.g.nodes[src].get("kind") == "person"
                and src not in links
            ):
                links[src] = {"person": src, "relation": data.get("label", "认识"), "direction": "in"}
        return list(links.values())

    def commit(self) -> None:
        with self._lock:
            self._persist()

    # --- editing / merging ----------------------------------------------
    def _copy_edge(self, subj: str, obj: str, data: dict) -> None:
        """Copy an edge onto (subj, obj), summing weight/count if it exists."""
        kind = data.get("kind")
        label = data.get("label")
        weight = data.get("weight", 1.0)
        count = data.get("count", 1)
        if self.g.has_edge(subj, obj):
            for _, d in self.g[subj][obj].items():
                if d.get("kind") == kind and d.get("label") == label:
                    d["weight"] = round(d.get("weight", 1.0) + weight, 4)
                    d["count"] = d.get("count", 1) + count
                    d["last_seen"] = time.time()
                    return
        self.g.add_edge(
            subj, obj, kind=kind, label=label, weight=weight, count=count,
            last_seen=time.time(),
        )

    def merge_person(self, source: str, target: str) -> None:
        """Redirect all of ``source``'s edges onto ``target`` and drop source."""
        with self._lock:
            source = self.resolve(source) or source
            target = self.resolve(target) or target
            if source == target or not self.g.has_node(source):
                return
            if not self.g.has_node(target):
                self.g.add_node(target, kind="person", count=1)
            aliases = set(self.g.nodes[target].get("aliases", []))
            aliases.update(self.g.nodes[source].get("aliases", []))
            aliases.add(source)
            self.g.nodes[target]["aliases"] = sorted(aliases)
            self.g.nodes[target]["count"] = (
                self.g.nodes[target].get("count", 0) + self.g.nodes[source].get("count", 0)
            )
            for _, tgt, data in list(self.g.out_edges(source, data=True)):
                if tgt != target:
                    self._copy_edge(target, tgt, data)
            for src, _, data in list(self.g.in_edges(source, data=True)):
                if src != target:
                    self._copy_edge(src, target, data)
            self.g.remove_node(source)

    def remove_trait(self, person: str, trait: str) -> None:
        with self._lock:
            person = self.resolve(person) or person
            node = f"trait:{trait}"
            while self.g.has_edge(person, node):
                self.g.remove_edge(person, node)

    def remove_preference(self, person: str, pref: str) -> None:
        with self._lock:
            person = self.resolve(person) or person
            node = f"pref:{pref}"
            while self.g.has_edge(person, node):
                self.g.remove_edge(person, node)

    def decay(self, factor: float) -> None:
        with self._lock:
            for _, _, data in self.g.edges(data=True):
                data["weight"] = round(data.get("weight", 1.0) * factor, 4)

    # ----------------------------------------------------------------- reads
    def neighbors(self, name: str) -> dict:
        """Return traits / preferences / relations attached to a person."""
        if not self.g.has_node(name):
            # try alias resolution
            name = self.resolve(name) or name
        if not self.g.has_node(name):
            return {"traits": [], "preferences": [], "relations": []}
        traits, prefs, rels = [], [], []
        for _, tgt, data in self.g.out_edges(name, data=True):
            entry = {"target": self.g.nodes[tgt].get("label", tgt), "label": data.get("label"),
                     "weight": data.get("weight", 1.0), "count": data.get("count", 1)}
            if data.get("kind") == "trait":
                traits.append(entry)
            elif data.get("kind") == "preference":
                prefs.append(entry)
            elif data.get("kind") == "relation":
                rels.append(entry)
        traits.sort(key=lambda x: x["weight"], reverse=True)
        prefs.sort(key=lambda x: x["weight"], reverse=True)
        rels.sort(key=lambda x: x["weight"], reverse=True)
        return {"traits": traits, "preferences": prefs, "relations": rels}

    def resolve(self, name: str) -> str | None:
        """Resolve an alias to a canonical person node, if possible."""
        if self.g.has_node(name):
            return name
        for node, data in self.g.nodes(data=True):
            if data.get("kind") == "person" and name in data.get("aliases", []):
                return node
        return None

    def persons(self) -> list[str]:
        return [n for n, d in self.g.nodes(data=True) if d.get("kind") == "person"]

    def export(self) -> dict:
        """Graph in a vis-network friendly shape (nodes + edges)."""
        nodes = []
        for n, d in self.g.nodes(data=True):
            nodes.append(
                {
                    "id": n,
                    "label": d.get("label", n),
                    "group": d.get("kind", "entity"),
                    "count": d.get("count", 1),
                }
            )
        edges = []
        for s, t, d in self.g.edges(data=True):
            edges.append(
                {
                    "from": s,
                    "to": t,
                    "label": d.get("label", ""),
                    "kind": d.get("kind", "relation"),
                    "weight": d.get("weight", 1.0),
                }
            )
        return {"nodes": nodes, "edges": edges}
