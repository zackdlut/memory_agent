"""测试用例：人物对话数据集。

用一组全新的人物（一个产品团队）系统性覆盖记忆系统的各项能力：
  - 稳定人设 / 特质 / 偏好 (traits / preferences)
  - 人物关系 (relations)
  - 行为模式：触发条件 -> 行为 (behavior patterns)
  - 情绪强烈 (高 emotion_intensity，会被自进化加权)
  - 任务相关 (task_related)
  - 重复出现 (近义对话，用于验证记忆 Merge)
  - 别名 / 昵称 (alias resolution)

用法：
  python -m scripts.test_cases            # 仅打印用例清单
  python -m scripts.test_cases --ingest   # 把全部对话写入记忆
  python -m scripts.test_cases --demo     # 写入后再跑建议的问答/预测用例
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# 人物设定（仅作参考，系统会自行从对话中抽取）
#   林然 / 小然 : 后端工程师，内向、自律，压力大时狂喝咖啡，养了一只猫
#   David       : 产品经理，外向健谈，爱社交，遇到冲突倾向先沟通
#   Mia         : 设计师，完美主义，对截稿焦虑，喜欢手冲咖啡与插画
#   老王 / 王哥 : 团队 leader，务实重结果，发火声音大但事后会道歉
# ---------------------------------------------------------------------------

TEST_CASES: list[dict] = [
    {
        "id": "trait_lin",
        "tests": "稳定人设 / 特质 / 偏好",
        "dialogue": """林然: 我习惯晚上写代码，越安静越能进入状态，白天反而效率低。
David: 你真是个典型的夜猫子工程师。
林然: 是啊，我话不多，但代码一写就是一整夜。""",
    },
    {
        "id": "pref_mia",
        "tests": "偏好 / 完美主义特质",
        "dialogue": """Mia: 这个按钮的圆角差了 1px，我必须改到完全对齐才安心。
David: 你对细节真的很较真。
Mia: 设计就是细节，差一点我都觉得难受。""",
    },
    {
        "id": "relation_team",
        "tests": "人物关系 (relations)",
        "dialogue": """老王: David 是我们组的产品经理，林然负责后端，Mia 管设计。
David: 对，我和林然搭档两年了，配合很默契。
Mia: 我平时主要对接 David 的需求。""",
    },
    {
        "id": "behavior_lin_stress",
        "tests": "行为模式：触发(压力大) -> 行为(狂喝咖啡)",
        "dialogue": """David: 林然，你今天怎么喝了第五杯咖啡了？
林然: 一到 deadline 前我就压力大，只能靠咖啡顶着。
David: 你每次赶工都这样。""",
    },
    {
        "id": "behavior_david_conflict",
        "tests": "行为模式：触发(冲突) -> 行为(先沟通)",
        "dialogue": """Mia: 上次需求吵起来，David 没有发火，反而约我单独聊。
林然: 他遇到分歧总是先找人沟通，不喜欢硬碰硬。
Mia: 嗯，所以和他合作很安心。""",
    },
    {
        "id": "emotion_high",
        "tests": "情绪强烈 (高 emotion_intensity)",
        "dialogue": """Mia: 我熬了三个通宵的方案被客户全盘否定了，我真的快崩溃了，太难受了！
David: 别急，我陪你一起想办法，这真的不是你的问题。
Mia: 谢谢你……我现在特别委屈又生气。""",
    },
    {
        "id": "task_related",
        "tests": "任务相关 (task_related=true)",
        "dialogue": """老王: 这个版本周五必须上线，登录模块的 bug 是最高优先级。
林然: 我今晚加班把登录的崩溃问题修好。
老王: 好，修完同步给 David 测试。""",
    },
    {
        "id": "behavior_wang_anger",
        "tests": "行为模式：触发(发火) -> 行为(事后道歉)",
        "dialogue": """David: 早会上老王又拍桌子了，声音特别大。
Mia: 但他下午私下跟我道歉了，说自己语气太冲。
David: 他就是这样，发完火会主动认错。""",
    },
    {
        "id": "repeat_lin_coffee",
        "tests": "重复出现 (与 behavior_lin_stress 近义，验证 Merge)",
        "dialogue": """林然: 又到交付前了，我已经连着喝了好几杯咖啡提神。
David: 你一紧张赶进度就猛灌咖啡，注意身体啊。
林然: 没办法，压力一大就停不下来。""",
    },
    {
        "id": "alias_lin",
        "tests": "别名 / 昵称 (小然 == 林然)",
        "dialogue": """老王: 小然这次登录模块修得很快，质量也高。
David: 是啊，林然加班一晚就搞定了。
老王: 这小伙子靠谱。""",
    },
    {
        "id": "pref_david_social",
        "tests": "偏好 / 外向社交特质",
        "dialogue": """David: 我最喜欢周末组局吃饭，认识新朋友让我充满能量。
Mia: 你简直是团队里的社交中心。
David: 哈哈，我一个人待着反而无聊。""",
    },
    {
        "id": "relation_pet",
        "tests": "关系 (人物 -> 实体：林然养猫)",
        "dialogue": """林然: 我养了一只橘猫叫『布丁』，加班时它就趴在我键盘边。
Mia: 难怪你头像是猫，太可爱了。
林然: 它是我下班后最大的安慰。""",
    },
]


# 建议的问答用例（--demo 时运行）
ASK_CASES = [
    "林然是个怎样的人？",
    "老王发火之后通常会怎么做？",
    "团队里谁最外向、最爱社交？",
    "Mia 对工作的态度是怎样的？",
    "小然养了什么宠物？",  # 测试别名 + 关系
]

# 建议的行为预测用例：(人物, 情境)
PREDICT_CASES = [
    ("林然", "下周一是一个重要版本的交付日"),
    ("David", "团队对某个方案产生了严重分歧"),
    ("老王", "他在会议上又因为进度落后发了脾气"),
    ("Mia", "她的设计稿被要求大改"),
]


def print_catalog() -> None:
    print(f"共 {len(TEST_CASES)} 条人物对话测试用例：\n")
    for i, case in enumerate(TEST_CASES, 1):
        print(f"[{i:02d}] ({case['id']}) — {case['tests']}")
        for line in case["dialogue"].splitlines():
            print(f"      {line}")
        print()
    print("建议问答用例：")
    for q in ASK_CASES:
        print(f"  - {q}")
    print("\n建议行为预测用例：")
    for person, sit in PREDICT_CASES:
        print(f"  - {person} @ {sit}")


def ingest_all() -> None:
    from app.agent import agent

    print("写入测试对话中...\n")
    for i, case in enumerate(TEST_CASES, 1):
        resp = agent.ingest(case["dialogue"], source="test_cases")
        ents = ", ".join(e.name for e in resp.entities) or "-"
        print(f"  [{i:02d}/{len(TEST_CASES)}] {resp.evolution['action']:>6} "
              f"(w={resp.evolution['weight']}) | {case['id']:<22} | entities: {ents}")
    print("\n写入完成。记忆统计：", agent.store.stats())


def run_demo() -> None:
    from app.agent import agent

    print("\n========== 问答（理解人）==========")
    for q in ASK_CASES:
        ans = agent.ask(q)
        srcs = ", ".join(sorted({m.source for m in ans.used_memories})) or "无"
        print(f"\nQ: {q}\nA: {ans.answer.strip()[:240]}\n   [命中来源: {srcs}]")

    print("\n========== 行为预测（Theory of Mind）==========")
    for person, sit in PREDICT_CASES:
        p = agent.predict(person, sit)
        print(f"\n{person} @ {sit}\n  -> {p.predicted_action}  (置信度 {p.confidence:.0%})\n     依据: {p.reasoning.strip()[:160]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="人物对话测试用例")
    parser.add_argument("--ingest", action="store_true", help="把全部对话写入记忆")
    parser.add_argument("--demo", action="store_true", help="写入后运行建议的问答/预测用例")
    args = parser.parse_args()

    if not args.ingest and not args.demo:
        print_catalog()
        return

    ingest_all()
    if args.demo:
        run_demo()


if __name__ == "__main__":
    main()
