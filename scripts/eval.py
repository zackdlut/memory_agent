"""Lightweight evaluation of the three PRD success metrics.

  - entity_accuracy     : did ingestion extract the expected people?
  - recall_accuracy      : does retrieval surface the expected memory for a query?
  - prediction_accuracy  : does behavior prediction mention the expected action?

This is a smoke-test style eval over a tiny labelled set (built on top of the
seed conversations); it is meant to make the metrics tangible and runnable,
not to be a rigorous benchmark.

Run:  python -m scripts.eval
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent import agent  # noqa: E402
from app.schemas import Entity, Episode, ExtractionResult  # noqa: E402
from scripts.seed import CONVERSATIONS  # noqa: E402
from scripts.test_cases import ASK_CASES  # noqa: E402

# (conversation, expected person names)
ENTITY_CASES = [
    (CONVERSATIONS[0], {"Alice", "Bob"}),
    (CONVERSATIONS[3], {"Carol", "Alice"}),
]

# (query, keyword that should appear in a retrieved memory)
RECALL_CASES = [
    ("Alice 周末喜欢做什么？", ["爬山", "山", "加班"]),
    ("Bob 是个怎样的人？", ["宅", "家", "游戏"]),
    ("Carol 喜欢什么？", ["咖啡", "社交", "朋友", "拍照"]),
    (ASK_CASES[0], ["林然", "工程师", "夜猫子", "安静"]),
    (ASK_CASES[1], ["老王", "道歉", "发火"]),
    (ASK_CASES[2], ["David", "外向", "社交"]),
]

# (person, situation, keywords any of which counts as correct)
PREDICTION_CASES = [
    ("Alice", "这个周末天气很好", ["爬山", "山", "户外", "运动"]),
    ("Bob", "朋友约他周末出门", ["拒绝", "家", "宅", "不"]),
]


def _hit(text: str, keywords: list[str]) -> bool:
    return any(k.lower() in text.lower() for k in keywords)


def eval_entities() -> float:
    ok = 0
    for conv, expected in ENTITY_CASES:
        resp = agent.ingest(conv, source="eval")
        names = {e.name for e in resp.entities}
        matched = len(expected & names) / len(expected)
        ok += matched
        print(f"  entity: expected {expected} got {names} -> {matched:.2f}")
    return ok / len(ENTITY_CASES)


def eval_recall() -> float:
    ok = 0
    for query, keywords in RECALL_CASES:
        items = agent.retriever.retrieve(query, rerank=False)
        blob = " ".join(m.text for m in items)
        hit = _hit(blob, keywords)
        ok += 1 if hit else 0
        print(f"  recall: '{query}' -> {'HIT' if hit else 'MISS'}")
    return ok / len(RECALL_CASES)


def eval_prediction() -> float:
    ok = 0
    for person, situation, keywords in PREDICTION_CASES:
        pred = agent.predict(person, situation)
        text = pred.predicted_action + " " + " ".join(pred.alternatives) + " " + pred.reasoning
        hit = _hit(text, keywords)
        ok += 1 if hit else 0
        print(f"  predict: {person} @ '{situation}' -> '{pred.predicted_action[:40]}' "
              f"[{'HIT' if hit else 'MISS'}]")
    return ok / len(PREDICTION_CASES)


def eval_alias_resolve() -> float:
    resolved = agent.resolver.resolve("小然")
    # substring match against existing 林然 if present, or after alias ingest
    hit = resolved == "林然"
    print(f"  alias_resolve: 小然 -> {resolved!r} [{'HIT' if hit else 'MISS'}]")
    return 1.0 if hit else 0.0


def eval_merge_no_duplicate() -> float:
    r1 = agent.resolver.normalize_extraction(
        ExtractionResult(
            entities=[Entity(name="林然", traits=["工程师"])],
            episode=Episode(summary="老王提到林然"),
        )
    )
    agent.evolver.ingest(r1)
    r2 = agent.resolver.normalize_extraction(
        ExtractionResult(
            entities=[Entity(name="小然", traits=["靠谱"])],
            episode=Episode(summary="老王提到小然"),
        )
    )
    agent.evolver.ingest(r2)
    p_lin = agent.store.persona.get("林然")
    p_xiao = agent.store.persona.get("小然")
    hit = p_lin is not None and (p_xiao is None or p_xiao.name == "林然")
    print(f"  merge_no_duplicate: {'HIT' if hit else 'MISS'} (林然={p_lin is not None})")
    return 1.0 if hit else 0.0


def main() -> None:
    print("== Entity accuracy ==")
    e = eval_entities()
    print("== Recall accuracy ==")
    r = eval_recall()
    print("== Prediction accuracy ==")
    p = eval_prediction()
    print("== Alias resolve ==")
    a = eval_alias_resolve()
    print("== Merge no duplicate ==")
    m = eval_merge_no_duplicate()
    print("\n================ RESULTS ================")
    print(f"  entity_accuracy      : {e:.2f}")
    print(f"  recall_accuracy      : {r:.2f}")
    print(f"  prediction_accuracy  : {p:.2f}")
    print(f"  alias_resolve        : {a:.2f}")
    print(f"  merge_no_duplicate   : {m:.2f}")


if __name__ == "__main__":
    main()
