"""Scan persona memory for likely duplicate people and optionally merge them.

Duplicates are detected with the same conservative rules the EntityResolver
uses at ingest time (alias membership, true substring, shared-suffix Chinese
nicknames). This catches pairs that were created *before* the resolver existed.

Usage:
  python -m scripts.migrate_duplicate_persons            # dry-run, list pairs
  python -m scripts.migrate_duplicate_persons --apply    # perform the merges
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent import agent  # noqa: E402
from app.entity.resolver import EntityResolver  # noqa: E402


def find_duplicate_pairs() -> list[tuple[str, str]]:
    """Return (source, target) pairs where source should fold into target."""
    resolver = EntityResolver(agent.store)
    personas = agent.store.persona.all()
    pairs: list[tuple[str, str]] = []
    seen: set[frozenset[str]] = set()

    for i, a in enumerate(personas):
        for b in personas[i + 1 :]:
            key = frozenset({a.name, b.name})
            if key in seen:
                continue

            is_dup = (
                b.name in a.aliases
                or a.name in b.aliases
                or resolver._is_substring_alias(a.name, b.name)
                or resolver._is_substring_alias(b.name, a.name)
                or resolver._suffix_nickname_match_pair(a.name, b.name)
            )
            if not is_dup:
                continue

            target = resolver._prefer_canonical_name(a.name, b.name)
            source = b.name if target == a.name else a.name
            pairs.append((source, target))
            seen.add(key)

    return pairs


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge duplicate persona nodes")
    parser.add_argument("--apply", action="store_true", help="perform the merges")
    args = parser.parse_args()

    pairs = find_duplicate_pairs()
    if not pairs:
        print("未发现疑似重复人物。")
        return

    print(f"发现 {len(pairs)} 对疑似重复人物：\n")
    for source, target in pairs:
        print(f"  '{source}'  ->  合并入  '{target}'")

    if not args.apply:
        print("\n（dry-run。加 --apply 执行合并。）")
        return

    print("\n开始合并...")
    for source, target in pairs:
        if agent.store.persona.get_exact(source) is None:
            print(f"  跳过 '{source}'（已不存在，可能已被前一次合并吸收）")
            continue
        agent.resolver.merge_person(source, target)
        print(f"  已合并 '{source}' -> '{target}'")
    print("\n完成。人物统计：", agent.store.stats())


if __name__ == "__main__":
    main()
