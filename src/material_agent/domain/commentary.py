import logging
from collections import Counter
from pathlib import Path
import re
import zlib

from ..clients.protocol import BackendClient
from ..utils.constants import dim_label, scene_label

_log = logging.getLogger("material_agent")

_DIM_PRIORITY = [
    "clarity",
    "exposure",
    "lighting",
    "composition",
    "color",
    "subject",
    "depth",
    "mood",
    "sharpness",
]

_GROUP_SUGGESTIONS = {
    "clarity": "拍摄时优先把快门再提一点并稳住机位，先保住主体清晰。",
    "exposure": "拍摄时优先保住主体亮度，别让人物完全陷进黑位。",
    "lighting": "拍摄时尽量等主光落到主体上再按快门。",
    "composition": "拍摄时多挪半步清理边缘干扰，让主体位置更利落。",
    "color": "拍摄时尽量避开最脏的混色灯位，减少后面校色压力。",
    "subject": "拍摄时等姿态、表情或动作更成立的瞬间再按快门。",
    "depth": "拍摄时尝试换机位，把前后层次再拉开一点。",
    "mood": "拍摄时让灯光节奏和主体状态更统一，先把氛围感拍完整。",
    "sharpness": "拍摄时先保住对焦和机身稳定，别让糊片拖掉整组完成度。",
}

_POST_SUGGESTIONS = {
    "clarity": "后期只做轻微锐化和降噪，避免把噪点一起拉起来。",
    "exposure": "后期先提一点阴影并压住刺眼高光，让主体更稳。",
    "lighting": "后期优先把主体亮度和局部明暗层次拉开。",
    "composition": "后期适当裁掉边缘干扰，让主体更集中。",
    "color": "后期先校正偏色，再轻压过脏的饱和度。",
    "subject": "后期通过适度裁切和局部提亮，把注意力重新收回主体。",
    "depth": "后期可以轻压背景亮度，让前后层次更明显。",
    "mood": "后期统一整体色调和反差，让氛围别散掉。",
    "sharpness": "后期锐化要保守一点，优先保住可看的细节而不是硬拉。",
}

_GROUP_SUGGESTIONS_EN = {
    "clarity": "Use a slightly faster shutter speed and stabilize the camera to protect subject clarity.",
    "exposure": "Protect subject brightness first and do not let the subject sink completely into the shadows.",
    "lighting": "Wait for the key light to land cleanly on the subject before pressing the shutter.",
    "composition": "Take half a step to clean up edge distractions and place the subject more decisively.",
    "color": "Avoid the dirtiest mixed-light positions to reduce later color-correction pressure.",
    "subject": "Wait for a stronger gesture, expression, or action before taking the shot.",
    "depth": "Try a different camera position to create more separation between foreground and background.",
    "mood": "Align lighting rhythm and subject state more closely so the mood feels complete.",
    "sharpness": "Protect focus and camera stability first so softness does not drag the whole set down.",
}

_POST_SUGGESTIONS_EN = {
    "clarity": "Apply sharpening and noise reduction lightly so noise does not become more obvious.",
    "exposure": "Lift the shadows slightly and control harsh highlights so the subject feels more stable.",
    "lighting": "Prioritize subject brightness and local tonal separation in post.",
    "composition": "Crop away edge distractions so the subject feels more focused.",
    "color": "Correct color cast first, then gently reduce dirty oversaturation.",
    "subject": "Use a modest crop and local brightness adjustments to pull attention back to the subject.",
    "depth": "Lower background brightness slightly to make spatial separation clearer.",
    "mood": "Unify the overall tone and contrast so the atmosphere does not fall apart.",
    "sharpness": "Keep sharpening conservative and preserve usable detail instead of forcing it.",
}

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_LATIN_WORD_RE = re.compile(r"\b[a-zA-Z]{3,}\b")


def _strip_known_prefix(text: str, prefix: str) -> str:
    body = (text or "").strip()
    if body.startswith(prefix):
        body = body[len(prefix) :].strip()
    return body


def _looks_language_mismatched(text: str, output_language: str = "zh") -> bool:
    body = (text or "").strip()
    if not body:
        return False
    cjk_chars = len(_CJK_RE.findall(body))
    latin_words = _LATIN_WORD_RE.findall(body)
    if output_language == "zh":
        return cjk_chars < 2 and len(latin_words) >= 4
    return cjk_chars >= 4 and len(latin_words) < 2


def group_issues_prefix(output_language: str = "zh") -> str:
    return "Group issues:" if output_language == "en" else "【组内问题】"


def shooting_advice_prefix(output_language: str = "zh") -> str:
    return "Shooting advice:" if output_language == "en" else "【拍摄建议】"


def post_advice_prefix(output_language: str = "zh") -> str:
    return "Post advice:" if output_language == "en" else "【后期指导】"


def rank_description(rank: int, group_size: int, output_language: str = "zh") -> str:
    if output_language == "en":
        return (
            f"Group ranking: this photo ranks #{rank} out of {group_size} photos in the group."
        )
    return f"【组内排名】这组共 {group_size} 张照片，这张综合评分排第 {rank}。"


def format_group_commentary(issues: str, shooting: str, output_language: str = "zh") -> str:
    return f"{group_issues_prefix(output_language)}{issues}\n{shooting_advice_prefix(output_language)}{shooting}"


def format_post_commentary(post: str, output_language: str = "zh") -> str:
    return f"{post_advice_prefix(output_language)}{post}"


def split_group_commentary_sections(text: str, output_language: str = "zh") -> tuple[str, str]:
    shooting_prefix = shooting_advice_prefix(output_language)
    if shooting_prefix in text:
        parts = text.split(shooting_prefix, 1)
        return parts[0].strip(), f"{shooting_prefix}{parts[1].strip()}"
    return text, ""


def _pick_weak_dims(score_maps: list[dict[str, float]]) -> list[str]:
    averages: list[tuple[float, int, str]] = []
    for index, dim in enumerate(_DIM_PRIORITY):
        values = [
            float(scores[dim])
            for scores in score_maps
            if dim in scores and isinstance(scores[dim], (int, float))
        ]
        if values:
            averages.append((sum(values) / len(values), index, dim))
    averages.sort(key=lambda item: (item[0], item[1]))
    return [dim for _, _, dim in averages[:2]]


def _format_dim_list_cn(dims: list[str]) -> str:
    labels = [dim_label(dim, "zh") for dim in dims]
    if not labels:
        return "整体完成度"
    if len(labels) == 1:
        return labels[0]
    return "和".join(labels)


def _format_dim_list_en(dims: list[str]) -> str:
    labels = [dim_label(dim, "en") for dim in dims]
    if not labels:
        return "overall quality"
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return ", ".join(labels[:-1]) + f", and {labels[-1]}"


def _ranked_dim_pairs(
    scores: dict[str, float] | None,
    *,
    reverse: bool = False,
    limit: int = 3,
) -> list[tuple[str, float]]:
    if not scores:
        return []
    ranked: list[tuple[int, float, str]] = []
    for index, dim in enumerate(_DIM_PRIORITY):
        value = scores.get(dim)
        if isinstance(value, (int, float)):
            ranked.append((index, float(value), dim))
    ranked.sort(key=lambda item: (-item[1], item[0]) if reverse else (item[1], item[0]))
    return [(dim, score) for _, score, dim in ranked[:limit]]


def _format_ranked_dims(
    scores: dict[str, float] | None,
    *,
    output_language: str = "zh",
    reverse: bool = False,
    limit: int = 3,
) -> str:
    pairs = _ranked_dim_pairs(scores, reverse=reverse, limit=limit)
    return ", ".join(
        f"{dim_label(dim, output_language)}={score:.1f}" for dim, score in pairs
    )


def _format_visible_breakdown(
    visible_breakdown: dict[str, float] | None,
    *,
    output_language: str = "zh",
    limit: int = 4,
) -> str:
    if not visible_breakdown:
        return ""
    items = [
        (key, float(value))
        for key, value in visible_breakdown.items()
        if isinstance(value, (int, float))
    ]
    if not items:
        return ""
    items.sort(key=lambda item: item[1])
    return ", ".join(
        f"{dim_label(dim, output_language)}={score:.1f}" for dim, score in items[:limit]
    )


def _average_dim_scores(score_maps: list[dict[str, float]] | None) -> dict[str, float]:
    if not score_maps:
        return {}
    averages: dict[str, float] = {}
    for dim in _DIM_PRIORITY:
        values = [
            float(scores[dim])
            for scores in score_maps
            if isinstance(scores, dict) and isinstance(scores.get(dim), (int, float))
        ]
        if values:
            averages[dim] = sum(values) / len(values)
    return averages


def _dominant_scenes(
    score_maps: list[dict[str, float]] | None,
    *,
    limit: int = 2,
) -> list[str]:
    if not score_maps:
        return []
    counts = Counter(
        scene.strip()
        for scores in score_maps
        if isinstance(scores, dict)
        for scene in [scores.get("_scene")]
        if isinstance(scene, str) and scene.strip()
    )
    return [scene for scene, _ in counts.most_common(limit)]


def _format_scene_focus(scenes: list[str], output_language: str = "zh") -> str:
    labels = [scene_label(scene, output_language) for scene in scenes if scene]
    if not labels:
        return ""
    if output_language == "en":
        if len(labels) == 1:
            return f"{labels[0]} scenes"
        return f"{' and '.join(labels)} scenes"
    if len(labels) == 1:
        return f"{labels[0]}场景"
    return f"{'和'.join(labels)}场景"


def _scene_context(scene: str | None, scene_raw: str = "") -> str:
    raw = (scene_raw or "").strip()
    if any(token in raw for token in ("舞台", "歌手", "演唱", "表演", "乐手", "主唱")):
        return "stage"
    if any(token in raw for token in ("露营", "营地", "篝火", "帐篷", " camp", "Camp")):
        return "camp"
    if scene == "city" and any(token in raw for token in ("夜", "街", "霓虹", "雨夜", "城市")):
        return "city_night"
    if scene == "detail" and any(token in raw for token in ("产品", "展台", "护肤", "展示")):
        return "product"
    if scene == "animals":
        return "animals"
    return scene or "default"


def _dominant_scene_raw(score_details: list[dict[str, float]] | None) -> str:
    if not score_details:
        return ""
    counts = Counter(
        raw.strip()
        for detail in score_details
        for raw in [detail.get("_scene_raw", "")]
        if isinstance(raw, str) and raw.strip()
    )
    return counts.most_common(1)[0][0] if counts else ""


def _variant_index(variant_key: str | None, count: int) -> int:
    if count <= 1:
        return 0
    if not variant_key:
        return 0
    return zlib.adler32(variant_key.encode("utf-8")) % count


def _variant_pick(options: list[str], variant_key: str | None) -> str:
    if not options:
        return ""
    return options[_variant_index(variant_key, len(options))]


def _looks_like_low_value_group_shooting_advice(text: str, output_language: str = "zh") -> bool:
    body = text.strip()
    if not body:
        return True
    if output_language == "en":
        action_markers = (
            "while shooting",
            "before pressing the shutter",
            "shutter speed",
            "camera position",
            "reposition",
            "key light",
            "wait for",
            "stabilize",
            "focus",
        )
        restatement_markers = (
            "improve sharpness",
            "improve saturation",
            "ensure the subject is clear",
            "ensure the subject stays clear",
            "keep the subject clear",
            "make the colors more vivid",
        )
        lowered = body.lower()
        return not any(marker in lowered for marker in action_markers) and any(
            marker in lowered for marker in restatement_markers
        )

    action_markers = (
        "拍摄时",
        "按快门",
        "快门",
        "机位",
        "主光",
        "补光",
        "对焦",
        "稳住",
        "等",
        "避开",
        "连拍",
    )
    restatement_markers = (
        "提升锐度",
        "提升色彩饱和度",
        "色彩饱和度",
        "主体清晰",
        "色彩鲜明",
        "加强细节表现",
        "确保",
    )
    generic_stability_only_markers = (
        "三脚架",
        "稳定机身",
        "手持抖动",
        "避免手持抖动",
    )
    return (
        not any(marker in body for marker in action_markers)
        and any(marker in body for marker in restatement_markers)
    ) or (
        any(marker in body for marker in generic_stability_only_markers)
        and not any(marker in body for marker in ("机位", "主光", "补光", "避开", "等"))
    )


def _scene_subject_hint(
    scene: str | None,
    output_language: str = "zh",
    *,
    scene_raw: str = "",
    decision: str | None = None,
    rank: int | None = None,
    group_size: int | None = None,
) -> str:
    context = _scene_context(scene, scene_raw)
    if output_language == "en":
        if decision == "reject":
            return "pull the frame back to a usable baseline before styling it"
        if rank is not None and group_size and rank == 1:
            return "protect what already makes this frame one of the better picks in the set"
        hints = {
            "people": "protect the person and the surrounding separation first",
            "city": "protect the building and light layering first",
            "landscape": "protect distance separation and overall light atmosphere first",
            "indoor": "protect the subject and interior tonal rhythm first",
            "detail": "protect the local texture and edge definition first",
            "stage": "protect the stage moment, face light, and subject edges first",
            "camp": "protect the campfire glow and near-far atmosphere first",
            "city_night": "protect the neon rhythm and structural layering first",
            "product": "protect the product edge definition and controlled highlights first",
            "animals": "protect the animal posture and separation first",
        }
        return hints.get(context, hints.get(scene or "", "protect the main subject impression first"))
    if decision == "reject":
        return "先把能救回来的观感拉回及格线"
    if rank is not None and group_size and rank == 1:
        if context == "stage":
            return "先把这张在这组里已经靠前的舞台状态和轮廓稳住"
        if context == "camp":
            return "先把这张在这组里已经靠前的露营氛围和远近层次稳住"
        return "先把这张在这组里已经靠前的观感稳住"
    hints = {
        "people": "先把人物状态和轮廓保住",
        "city": "先把建筑和灯光层次保住",
        "landscape": "先把远近层次和主光氛围保住",
        "indoor": "先把主体和空间光线节奏保住",
        "detail": "先把局部纹理和主体边界保住",
        "stage": "先把舞台状态、主光落点和主体轮廓保住",
        "camp": "先把露营现场的火光、层次和整体氛围保住",
        "city_night": "先把夜景灯光节奏和空间层次保住",
        "product": "先把产品边缘、质感和受光控制保住",
        "animals": "先把动物状态、毛发边缘和主体分离保住",
    }
    return hints.get(context, hints.get(scene or "", "先把主体观感保住"))


def _post_action_clause(
    dim: str,
    output_language: str = "zh",
    *,
    scene: str | None = None,
    scene_raw: str = "",
) -> str:
    context = _scene_context(scene, scene_raw)
    if output_language == "en":
        clauses = {
            "clarity": "keep sharpening and noise reduction restrained so noise and blur do not get pushed together",
            "exposure": "lift the subject-side shadows first and hold back harsh highlights before they both collapse",
            "lighting": "separate the subject from the background with clearer local light contrast",
            "composition": "trim edge distractions so attention returns to the main subject faster",
            "color": "neutralize the cast first and then clean up dirty oversaturation",
            "subject": "use a modest crop and local emphasis so the subject stops losing attention",
            "depth": "hold back background brightness or contrast slightly to reopen spatial depth",
            "mood": "unify color temperature and contrast rhythm so the atmosphere stops drifting",
            "sharpness": "keep sharpening light and protect subject edges instead of forcing soft areas",
        }
        return clauses.get(
            dim,
            "start with light corrective edits and keep the main subject usable before styling",
        )
    context_clauses = {
        ("stage", "color"): "先压住舞台混色里最脏的部分，别让肤色和服装一起发灰发脏",
        ("stage", "lighting"): "把脸部或主体边缘的受光单独提出来，让舞台主光真正落在该看的位置",
        ("camp", "color"): "先守住火光和环境光的主色关系，别把露营氛围修成一片脏橙或死灰",
        ("camp", "depth"): "压掉边缘乱亮点，让帐篷、火光和背景黑位重新站开层次",
        ("city_night", "lighting"): "先把路灯和霓虹的亮部层次分开，别让夜景高光糊成一片",
        ("city_night", "color"): "先把霓虹和环境光的偏色拆开校，别让夜景颜色互相串脏",
        ("product", "clarity"): "先把产品边缘和表面纹理救回来，锐化只落在该清楚的边界上",
        ("product", "lighting"): "先把产品主受光和反光压顺，别让高光硬顶在包装表面",
        ("animals", "clarity"): "先保住毛发和眼周边缘，锐化别把背景噪点一起拉起来",
        ("animals", "subject"): "用轻裁切和局部提亮把注意力重新收回动物姿态和眼神",
    }
    if (context, dim) in context_clauses:
        return context_clauses[(context, dim)]
    clauses = {
        "clarity": "锐化和降噪都收着做，别把噪点和拖影一起推出来",
        "exposure": "先把主体一侧的阴影提回一点，再压住跳出的高光",
        "lighting": "优先拉开主体和背景的局部明暗关系，让主光落点更明确",
        "composition": "适当裁掉边缘抢戏的区域，让视线重新回到主体",
        "color": "先校正偏色，再把脏掉的饱和度压干净，别让颜色互相打架",
        "subject": "用轻裁切和局部提亮把注意力重新收回主体",
        "depth": "轻压背景亮度或反差，把前后层次重新拉开",
        "mood": "统一整体色温和反差节奏，让氛围别散掉",
        "sharpness": "锐化只做轻量补偿，先保住主体边缘，别硬拉发虚区域",
    }
    return clauses.get(dim, "后期先做轻量校正，优先把主体观感拉回可用。")


def _group_scene_suggestion(
    dim: str,
    *,
    scene: str | None = None,
    scene_raw: str = "",
    output_language: str = "zh",
) -> str:
    context = _scene_context(scene, scene_raw)
    if output_language == "en":
        return _GROUP_SUGGESTIONS_EN.get(
            dim,
            "Protect subject state and technical stability first while shooting.",
        )
    context_suggestions = {
        ("stage", "clarity"): "拍摄时优先把快门再提一点并稳住机位，先保住舞台主体清晰",
        ("stage", "color"): "拍摄时尽量避开最脏的混色灯位，等颜色更干净的时候再按",
        ("stage", "lighting"): "拍摄时尽量等主光真正落到脸上或主体边缘再按快门",
        ("camp", "clarity"): "拍摄时先稳住机位或借支撑点，别让夜景微抖把营地细节磨掉",
        ("camp", "color"): "拍摄时先守住火光和环境光的主色关系，别让杂色光源把氛围冲散",
        ("camp", "exposure"): "拍摄时先保住火光和人物的亮部层次，别让高光直接死白",
        ("city_night", "lighting"): "拍摄时优先等路灯或霓虹形成清晰主光区，再决定按快门时机",
        ("city_night", "color"): "拍摄时尽量避开颜色最乱的灯位，先让夜景主色更干净",
        ("product", "clarity"): "拍摄时先把产品边缘和字样对实，别让关键细节先软掉",
        ("product", "lighting"): "拍摄时先控住包装反光，让主受光落在最想展示的面上",
        ("animals", "clarity"): "拍摄时先保住眼部或头部对焦，别让毛发边缘一开始就发虚",
        ("animals", "subject"): "拍摄时等姿态和朝向更成立的瞬间再按，别急着抢第一下",
    }
    return context_suggestions.get(
        (context, dim),
        _GROUP_SUGGESTIONS.get(dim, "拍摄时优先把主体状态和技术稳定性先保住。"),
    )


def build_group_commentary_input(
    group_summary: list[tuple[str, float]],
    score_details: list[dict[str, float]] | None = None,
    *,
    output_language: str = "zh",
) -> str:
    lines: list[str] = []
    score_details = score_details or []
    for index, (file_path, score) in enumerate(group_summary, start=1):
        detail = score_details[index - 1] if index - 1 < len(score_details) else {}
        if not isinstance(detail, dict):
            detail = {}
        parts = [f"{index}. {Path(file_path).name} total={score:.1f}"]
        scene = detail.get("_scene")
        if isinstance(scene, str) and scene.strip():
            parts.append(f"scene={scene_label(scene, output_language)}")
        scene_raw = detail.get("_scene_raw")
        if isinstance(scene_raw, str) and scene_raw.strip():
            parts.append(f"scene_raw={scene_raw.strip()}")
        decision = detail.get("_decision")
        if isinstance(decision, str) and decision.strip():
            parts.append(f"decision={decision.strip()}")
        weak = _format_ranked_dims(detail, output_language=output_language, limit=3)
        if weak:
            parts.append(f"weak={weak}")
        strong = _format_ranked_dims(
            detail,
            output_language=output_language,
            reverse=True,
            limit=2,
        )
        if strong:
            parts.append(f"strong={strong}")
        lines.append(" | ".join(parts))

    if score_details:
        recurring_weak = _pick_weak_dims(score_details)
        if recurring_weak:
            recurring_text = (
                _format_dim_list_en(recurring_weak)
                if output_language == "en"
                else _format_dim_list_cn(recurring_weak)
            )
            prefix = "Recurring weak dimensions:" if output_language == "en" else "组内反复偏弱维度："
            lines.append(f"{prefix} {recurring_text}")
    return "\n".join(lines)


def build_photo_commentary_context(
    score_line: str,
    *,
    scores: dict[str, float] | None = None,
    scene: str | None = None,
    scene_raw: str = "",
    decision: str | None = None,
    visible_breakdown: dict[str, float] | None = None,
    output_language: str = "zh",
) -> str:
    lines: list[str] = []
    if scene:
        scene_text = scene_label(scene, output_language)
        if scene_raw.strip():
            lines.append(f"Scene: {scene_text} | Scene detail: {scene_raw.strip()}")
        else:
            lines.append(f"Scene: {scene_text}")
    elif scene_raw.strip():
        lines.append(f"Scene detail: {scene_raw.strip()}")
    if decision:
        lines.append(f"Decision: {decision}")
    if score_line.strip():
        lines.append(f"Score summary: {score_line.strip()}")
    weak = _format_ranked_dims(scores, output_language=output_language, limit=3)
    if weak:
        lines.append(f"Weak dimensions: {weak}")
    strong = _format_ranked_dims(scores, output_language=output_language, reverse=True, limit=2)
    if strong:
        lines.append(f"Strong dimensions: {strong}")
    visible = _format_visible_breakdown(visible_breakdown, output_language=output_language)
    if visible:
        lines.append(f"Visible breakdown: {visible}")
    return "\n".join(lines)


def _synthesize_group_commentary(
    score_details: list[dict[str, float]] | None,
    output_language: str = "zh",
    *,
    variant_key: str | None = None,
) -> str:
    if not score_details:
        return ""
    weak_dims = _pick_weak_dims(score_details)
    if not weak_dims:
        return ""
    averages = _average_dim_scores(score_details)
    scenes = _dominant_scenes(score_details)
    scene_focus = _format_scene_focus(scenes, output_language)
    dominant_scene = scenes[0] if scenes else None
    dominant_scene_raw = _dominant_scene_raw(score_details)
    if output_language == "en":
        weak_text = ", ".join(
            f"{dim_label(dim, output_language)}={averages[dim]:.1f}"
            for dim in weak_dims
            if dim in averages
        )
        issue = f"The set repeatedly loses points on {weak_text or _format_dim_list_en(weak_dims)}"
        if scene_focus:
            issue += f", especially in {scene_focus}"
        issue += "."
        shooting_parts = [
            _GROUP_SUGGESTIONS_EN.get(
                dim,
                "Protect subject state and technical stability first while shooting.",
            )
            for dim in weak_dims[:2]
        ]
        if _variant_index(variant_key, 2) == 1:
            shooting_parts = list(reversed(shooting_parts))
        shooting = " ".join(dict.fromkeys(part for part in shooting_parts if part))
        return format_group_commentary(issue, shooting, output_language)

    weak_text = "和".join(
        f"{dim_label(dim, output_language)}={averages[dim]:.1f}"
        for dim in weak_dims
        if dim in averages
    ) or _format_dim_list_cn(weak_dims)
    issue = _variant_pick(
        [
            f"这组反复掉分的是{weak_text}",
            f"这组最拖后腿的是{weak_text}",
            f"这组持续拉分的是{weak_text}",
        ],
        variant_key,
    )
    if scene_focus:
        issue += f"，问题多出现在{scene_focus}"
    issue += "。"
    shooting_parts = [
        _group_scene_suggestion(
            dim,
            scene=dominant_scene,
            scene_raw=dominant_scene_raw,
            output_language=output_language,
        )
        for dim in weak_dims[:2]
    ]
    if _variant_index(variant_key, 2) == 1:
        shooting_parts = list(reversed(shooting_parts))
    shooting = "；".join(
        dict.fromkeys(part.rstrip("。") for part in shooting_parts if part)
    ).strip("；")
    if shooting:
        shooting += "。"
    return format_group_commentary(issue, shooting, output_language)


def _synthesize_post_commentary(
    scores: dict[str, float] | None,
    *,
    scene: str | None = None,
    scene_raw: str = "",
    decision: str | None = None,
    rank: int | None = None,
    group_size: int | None = None,
    variant_key: str | None = None,
    visible_breakdown: dict[str, float] | None = None,
    output_language: str = "zh",
) -> str:
    weak_pairs = _ranked_dim_pairs(scores, limit=2)
    if visible_breakdown:
        for dim, _ in _ranked_dim_pairs(visible_breakdown, limit=2):
            if dim not in {name for name, _ in weak_pairs}:
                weak_pairs.append((dim, float(visible_breakdown[dim])))
            if len(weak_pairs) >= 2:
                break
    weak_dims = [dim for dim, _ in weak_pairs[:2]]
    if not weak_dims:
        return ""
    if output_language == "en":
        weak_text = _format_dim_list_en(weak_dims)
        hint = _scene_subject_hint(
            scene,
            output_language,
            scene_raw=scene_raw,
            decision=decision,
            rank=rank,
            group_size=group_size,
        )
        opener = _variant_pick(
            [
                f"Prioritize {weak_text} first and {hint}",
                f"Start with {weak_text} first and {hint}",
                f"Do not overwork the frame yet; fix {weak_text} first and {hint}",
            ],
            variant_key,
        )
        clauses = [
            _post_action_clause(dim, output_language, scene=scene, scene_raw=scene_raw)
            for dim in weak_dims
        ]
        if _variant_index(variant_key, 2) == 1:
            clauses = list(reversed(clauses))
        body = "; ".join(dict.fromkeys([opener, *clauses])) + "."
        return format_post_commentary(body, output_language)

    weak_text = _format_dim_list_cn(weak_dims)
    hint = _scene_subject_hint(
        scene,
        output_language,
        scene_raw=scene_raw,
        decision=decision,
        rank=rank,
        group_size=group_size,
    )
    opener = _variant_pick(
        [
            f"这张更该先救{weak_text}，{hint}",
            f"这一张先别急着整体大动，先处理{weak_text}，{hint}",
            f"这张先从{weak_text}下手，{hint}",
        ],
        variant_key,
    )
    clauses = [
        _post_action_clause(dim, output_language, scene=scene, scene_raw=scene_raw)
        for dim in weak_dims
    ]
    if _variant_index(variant_key, 2) == 1:
        clauses = list(reversed(clauses))
    body = "；".join(dict.fromkeys([opener, *clauses])) + "。"
    return format_post_commentary(body, output_language)


def _fallback_group_commentary(
    score_details: list[dict[str, float]] | None,
    output_language: str = "zh",
    *,
    variant_key: str | None = None,
) -> str:
    return _synthesize_group_commentary(score_details, output_language, variant_key=variant_key)


def _fallback_post_commentary(
    scores: dict[str, float] | None,
    *,
    scene: str | None = None,
    scene_raw: str = "",
    decision: str | None = None,
    rank: int | None = None,
    group_size: int | None = None,
    variant_key: str | None = None,
    visible_breakdown: dict[str, float] | None = None,
    output_language: str = "zh",
) -> str:
    return _synthesize_post_commentary(
        scores,
        scene=scene,
        scene_raw=scene_raw,
        decision=decision,
        rank=rank,
        group_size=group_size,
        variant_key=variant_key,
        visible_breakdown=visible_breakdown,
        output_language=output_language,
    )


def regenerate_group_commentary(
    score_details: list[dict[str, float]] | None,
    *,
    variant_key: str | None = None,
    output_language: str = "zh",
) -> str:
    return _fallback_group_commentary(score_details, output_language, variant_key=variant_key)


def regenerate_post_commentary(
    scores: dict[str, float] | None,
    *,
    scene: str | None = None,
    scene_raw: str = "",
    decision: str | None = None,
    rank: int | None = None,
    group_size: int | None = None,
    variant_key: str | None = None,
    visible_breakdown: dict[str, float] | None = None,
    output_language: str = "zh",
) -> str:
    return _fallback_post_commentary(
        scores,
        scene=scene,
        scene_raw=scene_raw,
        decision=decision,
        rank=rank,
        group_size=group_size,
        variant_key=variant_key,
        visible_breakdown=visible_breakdown,
        output_language=output_language,
    )


def _should_refine_group_commentary(
    text: str,
    score_details: list[dict[str, float]] | None,
    output_language: str = "zh",
) -> bool:
    if not text.strip():
        return True
    if not score_details:
        return False
    issues, shooting = split_group_commentary_sections(text, output_language)
    issues_body = _strip_known_prefix(issues, group_issues_prefix(output_language))
    shooting_body = _strip_known_prefix(shooting, shooting_advice_prefix(output_language))
    if _looks_language_mismatched(issues_body, output_language) or _looks_language_mismatched(
        shooting_body, output_language
    ):
        return True
    weak_dims = _pick_weak_dims(score_details)
    weak_labels = {dim_label(dim, output_language) for dim in weak_dims}
    if len(issues_body) < 16 or len(shooting_body) < 16:
        return True
    if issues_body.count("=") >= 3 and "这组" not in issues_body and "set" not in issues_body.lower():
        return True
    if output_language == "en" and issues_body.startswith("The main weaknesses in this set are"):
        return True
    if output_language == "zh" and issues_body.startswith("这组照片主要短板在"):
        return True
    if output_language == "zh" and "曝光" in issues_body and not ({"曝光", "光线"} & weak_labels):
        return True
    if output_language == "en" and "exposure" in issues_body.lower() and not (
        {"Exposure", "Lighting"} & weak_labels
    ):
        return True
    if _looks_like_low_value_group_shooting_advice(shooting_body, output_language):
        return True
    return False


def _should_refine_post_commentary(
    text: str,
    scores: dict[str, float] | None,
    output_language: str = "zh",
) -> bool:
    body = _strip_known_prefix(text, post_advice_prefix(output_language))
    if not body:
        return True
    if _looks_language_mismatched(body, output_language):
        return True
    weak_dims = [dim for dim, _ in _ranked_dim_pairs(scores, limit=2)]
    weak_labels = {dim_label(dim, output_language) for dim in weak_dims}
    known_templates = (
        set(_POST_SUGGESTIONS_EN.values()) if output_language == "en" else set(_POST_SUGGESTIONS.values())
    )
    if body in known_templates:
        return True
    if len(body) < 24:
        return True
    if output_language == "zh":
        if "【组内问题】" in body or "【拍摄建议】" in body:
            return True
        shooting_markers = (
            "拍摄时",
            "按快门",
            "快门",
            "机位",
            "三脚架",
            "对焦",
            "补光",
            "侧逆光",
            "主光",
            "浅景深",
            "换机位",
        )
        if any(marker in body for marker in shooting_markers):
            return True
    else:
        if "Group issues:" in body or "Shooting advice:" in body:
            return True
        shooting_markers = (
            "while shooting",
            "press the shutter",
            "shutter speed",
            "tripod",
            "focus on",
            "camera position",
            "reposition",
            "key light",
        )
        lowered = body.lower()
        if any(marker in lowered for marker in shooting_markers):
            return True
    if output_language == "zh" and "曝光" in body and not ({"曝光", "光线"} & weak_labels):
        return True
    if output_language == "en" and "exposure" in body.lower() and not (
        {"Exposure", "Lighting"} & weak_labels
    ):
        return True
    return False


class CommentaryGenerator:
    def __init__(self, client: BackendClient, enabled: bool, output_language: str = "zh"):
        self.client = client
        self.enabled = enabled
        self.output_language = output_language

    async def for_group(
        self,
        group_summary: list[tuple[str, float]],
        score_details: list[dict[str, float]] | None = None,
    ) -> str:
        if not self.enabled or not group_summary:
            return ""
        group_data = build_group_commentary_input(
            group_summary,
            score_details,
            output_language=self.output_language,
        )
        variant_key = "|".join(Path(file_path).name for file_path, _ in group_summary[:4])
        try:
            text = await self.client.generate_group_commentary(group_data)
            if _should_refine_group_commentary(text, score_details, self.output_language):
                refined = _synthesize_group_commentary(
                    score_details,
                    self.output_language,
                    variant_key=variant_key,
                )
                if refined:
                    return refined
            return text
        except Exception as error:
            _log.warning("Group commentary failed (%s): %r", type(error).__name__, error)
            return _fallback_group_commentary(
                score_details,
                self.output_language,
                variant_key=variant_key,
            )

    async def for_photo(
        self,
        score_line: str,
        group_commentary: str,
        scores: dict[str, float] | None = None,
        *,
        scene: str | None = None,
        scene_raw: str = "",
        decision: str | None = None,
        rank: int | None = None,
        group_size: int | None = None,
        variant_key: str | None = None,
        visible_breakdown: dict[str, float] | None = None,
    ) -> str:
        if not self.enabled:
            return ""
        try:
            text = await self.client.generate_post_commentary(score_line, group_commentary)
            if _should_refine_post_commentary(text, scores, self.output_language):
                refined = _synthesize_post_commentary(
                    scores,
                    scene=scene,
                    scene_raw=scene_raw,
                    decision=decision,
                    rank=rank,
                    group_size=group_size,
                    variant_key=variant_key,
                    visible_breakdown=visible_breakdown,
                    output_language=self.output_language,
                )
                if refined:
                    return refined
            return text
        except Exception as error:
            _log.warning("Photo commentary failed (%s): %r", type(error).__name__, error)
            return _fallback_post_commentary(
                scores,
                scene=scene,
                scene_raw=scene_raw,
                decision=decision,
                rank=rank,
                group_size=group_size,
                variant_key=variant_key,
                visible_breakdown=visible_breakdown,
                output_language=self.output_language,
            )
