"""Canonical person-name resolution for ingest and retrieval."""

from __future__ import annotations

from app.config import settings
from app.memory.store import MemoryStore
from app.schemas import Entity, ExtractionResult


class EntityResolver:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def resolve(self, name: str) -> str | None:
        if not name or name == settings.assistant_name:
            return None
        persona = self.store.persona.get(name)
        if persona:
            return persona.name
        graph_name = self.store.semantic.resolve(name)
        if graph_name:
            return graph_name
        hit = self._substring_match_known(name)
        if hit:
            return hit
        return self._suffix_nickname_match(name)

    def _suffix_nickname_match(self, name: str) -> str | None:
        """Match Chinese nicknames that share a suffix (e.g. 小然 -> 林然)."""
        if len(name) < 2:
            return None
        suffix = name[-1]
        candidates = [
            p.name
            for p in self.store.persona.all()
            if p.name != name
            and p.name.endswith(suffix)
            and abs(len(p.name) - len(name)) <= 1
        ]
        if len(candidates) == 1:
            return candidates[0]
        return None

    @staticmethod
    def _is_substring_alias(short: str, long: str) -> bool:
        return len(short) >= 2 and short != long and short in long

    def _substring_match_known(self, name: str) -> str | None:
        """Map a nickname to an existing longer canonical name when unambiguous."""
        if len(name) < 2:
            return None
        matches: list[str] = []
        for p in self.store.persona.all():
            if self._is_substring_alias(name, p.name):
                matches.append(p.name)
            elif self._is_substring_alias(p.name, name):
                matches.append(p.name)
        if len(matches) == 1:
            return matches[0]
        return None

    @staticmethod
    def _prefer_canonical_name(a: str, b: str) -> str:
        if a.startswith("小") and not b.startswith("小"):
            return b
        if b.startswith("小") and not a.startswith("小"):
            return a
        return a if len(a) >= len(b) else b

    def _canonical_for_pair(self, a: Entity, b: Entity) -> tuple[str, str] | None:
        if b.name in a.aliases:
            return a.name, b.name
        if a.name in b.aliases:
            return b.name, a.name
        if self._is_substring_alias(a.name, b.name):
            return b.name, a.name
        if self._is_substring_alias(b.name, a.name):
            return a.name, b.name
        return None

    def _merge_same_round_entities(self, entities: list[Entity]) -> list[Entity]:
        if not entities:
            return []

        parent = {e.name: e.name for e in entities}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union_to(canon: str, other: str) -> None:
            ro, rc = find(other), find(canon)
            if ro != rc:
                parent[ro] = rc

        for i, a in enumerate(entities):
            for b in entities[i + 1 :]:
                pair = self._canonical_for_pair(a, b)
                if pair:
                    canon, alias = pair
                    union_to(canon, alias)
                elif self._suffix_nickname_match_pair(a.name, b.name):
                    canon = self._prefer_canonical_name(a.name, b.name)
                    other = b.name if canon == a.name else a.name
                    union_to(canon, other)

        by_canon: dict[str, Entity] = {}
        for e in entities:
            canon = find(e.name)
            if canon in by_canon:
                existing = by_canon[canon]
                existing.traits = sorted(set(existing.traits) | set(e.traits))
                existing.preferences = sorted(set(existing.preferences) | set(e.preferences))
                aliases = set(existing.aliases) | set(e.aliases)
                if e.name != canon:
                    aliases.add(e.name)
                existing.aliases = sorted(aliases)
            else:
                merged = Entity(**e.model_dump())
                merged.name = canon
                aliases = set(merged.aliases)
                if e.name != canon:
                    aliases.add(e.name)
                merged.aliases = sorted(aliases)
                by_canon[canon] = merged
        return list(by_canon.values())

    @staticmethod
    def _suffix_nickname_match_pair(a: str, b: str) -> bool:
        if len(a) < 2 or len(b) < 2 or a == b:
            return False
        return a[-1] == b[-1] and abs(len(a) - len(b)) <= 1

    def _canon(self, name: str, entity_map: dict[str, Entity]) -> str:
        if not name or name == settings.assistant_name:
            return name
        resolved = self.resolve(name)
        if resolved:
            return resolved
        if name in entity_map:
            return name
        for e in entity_map.values():
            if name in e.aliases:
                return e.name
        return name

    def _is_known_person(self, name: str, entity_map: dict[str, Entity]) -> bool:
        return bool(self.resolve(name) or name in entity_map)

    def merge_person(self, source: str, target: str) -> str | None:
        """Merge a duplicate ``source`` person into ``target`` across all stores."""
        if not source or not target or source == target:
            return self.resolve(target) or target
        self.store.persona.merge(source, target)
        self.store.semantic.merge_person(source, target)
        self.store.commit()
        return target

    def normalize_extraction(self, result: ExtractionResult) -> ExtractionResult:
        entities = [
            Entity(**e.model_dump())
            for e in result.entities
            if e.name and e.name != settings.assistant_name
        ]
        entities = self._merge_same_round_entities(entities)

        for e in entities:
            resolved = self.resolve(e.name)
            if resolved and resolved != e.name:
                e.aliases = sorted(set(e.aliases) | {e.name})
                e.name = resolved

        entity_map = {e.name: e for e in entities}

        relations = []
        for rel in result.relations:
            if settings.assistant_name in (rel.subject, rel.object):
                continue
            subj = self._canon(rel.subject, entity_map)
            obj = (
                self._canon(rel.object, entity_map)
                if self._is_known_person(rel.object, entity_map)
                else rel.object
            )
            relations.append(rel.model_copy(update={"subject": subj, "object": obj}))

        patterns = []
        for pat in result.behavior_patterns:
            if pat.person == settings.assistant_name:
                continue
            patterns.append(pat.model_copy(update={"person": self._canon(pat.person, entity_map)}))

        participants = sorted(
            {self._canon(p, entity_map) for p in result.episode.participants if p}
        )
        episode = result.episode.model_copy(update={"participants": participants})

        return ExtractionResult(
            entities=entities,
            relations=relations,
            behavior_patterns=patterns,
            episode=episode,
        )
