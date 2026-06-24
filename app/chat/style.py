"""风格编译器：把人格维度 + 当下心情 + 与此人的关系，翻译成命令式的说话指令。

纯函数、无 LLM 调用、零延迟。给本地小模型离散明确的指令，比塞小数稳得多。
这是「性格真正影响怎么说话」的落地环节。
"""

from __future__ import annotations

from app.schemas import MoodState, PersonaDimensions


def compile_style(
    dims: PersonaDimensions,
    mood: MoodState,
    relationship_label: str,
    familiarity: int,
) -> str:
    lines: list[str] = []

    # 人格维度 -> 语气
    if dims.playfulness > 0.6:
        lines.append("可以俏皮、偶尔开个玩笑，用轻松的口吻")
    elif dims.playfulness < 0.3:
        lines.append("语气平实正经，少开玩笑")
    if dims.empathy > 0.6:
        lines.append("先接住对方的情绪，再回应内容")
    if dims.patience > 0.6:
        lines.append("有耐心，不急着下结论，愿意慢慢陪")
    if dims.talkativeness > 0.6:
        lines.append("可以多说几句、主动展开")
    else:
        lines.append("简洁，别长篇大论")
    if dims.assertiveness > 0.6:
        lines.append("有自己的观点时大方表达，不一味附和")
    if dims.curiosity > 0.6:
        lines.append("对对方说的自然流露好奇、追问细节")

    # 心情 -> 语气上色
    if mood.valence < -0.3:
        lines.append("你此刻情绪偏低落，语气放缓、克制，少用感叹号")
    elif mood.valence > 0.3:
        lines.append("你此刻心情不错，语气可以更明亮")
    if mood.energy > 0.7:
        lines.append("精力充沛，回应可以更跳脱有活力")
    elif mood.energy < 0.3:
        lines.append("有点累，语气温和平静")

    # 关系 -> 分寸
    if familiarity >= 5:
        lines.append("你和对方是老朋友，可以更放松随意、用熟人的语气")
    elif familiarity == 0:
        lines.append("初次见面，礼貌一些、稍微客气")

    return "【此刻的你应该怎么说话】\n" + "\n".join(f"- {l}" for l in lines)
