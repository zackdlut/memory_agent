"""Seed the memory with a small multi-person story so the demo works instantly.

Run:  python -m scripts.seed
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent import agent  # noqa: E402

CONVERSATIONS = [
    """Alice: 我最近迷上了爬山，几乎每个周末都会去郊外的山里。
Bob: 你总是这么有活力，我更喜欢宅在家里打游戏。
Alice: 哈哈，我一闲下来就难受，必须找点事做。""",
    """Bob: Alice 又拉我去爬山了，但我拒绝了，我还是更想在家。
Carol: Bob 你真的很宅，每次约你出门都失败。
Bob: 没办法，安静的环境才让我放松。""",
    """Alice: 这次项目的 deadline 快到了，我打算这周末加班把它做完。
Carol: 你对工作也太拼了吧，连周末都不休息。
Alice: 重要的任务我一定会全力以赴，不然睡不着。""",
    """Carol: 我最喜欢周末和朋友去咖啡馆聊天，顺便拍照。
Alice: 你真是个社交达人，认识好多人。
Carol: 是啊，和人交流让我充电。""",
    """Bob: Alice 推荐我去看一部纪录片，关于登山者的，我居然看哭了。
Alice: 我就知道你嘴上说宅，其实内心也很有热情。
Bob: 被你发现了，我只是不爱出门而已。""",
]


def main() -> None:
    print("Seeding memory...")
    for i, conv in enumerate(CONVERSATIONS, 1):
        resp = agent.ingest(conv, source="seed")
        ents = ", ".join(e.name for e in resp.entities) or "-"
        print(f"  [{i}/{len(CONVERSATIONS)}] {resp.evolution['action']:>6} | "
              f"entities: {ents} | {resp.episode.summary[:50]}")
    print("\nDone. Memory stats:", agent.store.stats())


if __name__ == "__main__":
    main()
