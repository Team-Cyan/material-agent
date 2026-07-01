SCENE_LIST = [
    "people",
    "sports",
    "landscape",
    "city",
    "indoor",
    "detail",
    "animals",
    "other",
]

SCENE_LABELS = {
    "people": "人物",
    "sports": "运动",
    "landscape": "风光",
    "city": "城市",
    "indoor": "室内",
    "detail": "特写",
    "animals": "动物",
    "other": "其他",
}

SCENE_LABELS_EN = {
    "people": "People",
    "sports": "Sports",
    "landscape": "Landscape",
    "city": "City",
    "indoor": "Indoor",
    "detail": "Detail",
    "animals": "Animals",
    "other": "Other",
}

LEGACY_SCENE_MIGRATIONS = {
    "concert": "people",
    "portrait": "people",
    "landscape": "landscape",
    "cityscape": "city",
    "food": "detail",
    "indoor": "indoor",
    "macro": "detail",
    "sports": "sports",
    "wildlife": "animals",
    "other": "other",
    "street": "other",
    "travel": "other",
}

SCENE_LABEL_TO_KEY = {label: key for key, label in SCENE_LABELS.items()}
_SCENE_KEY_LOWER_SET = {scene.lower() for scene in SCENE_LIST}
_LEGACY_KEY_LOWER_TO_NEW = {legacy.lower(): new for legacy, new in LEGACY_SCENE_MIGRATIONS.items()}

_DISPLAY_ALIASES = {
    **SCENE_LABEL_TO_KEY,
    **{key: key for key in SCENE_LIST},
}

VISION_DIMS = [
    "subject",
    "composition",
    "lighting",
    "color",
    "clarity",
    "depth",
    "mood",
]

VISION_ABBR = ["subj", "comp", "lit", "color", "clar", "dep", "mood"]
ALL_DIMS = ["exposure", "sharpness"] + VISION_DIMS
ALL_ABBR = ["exp", "sharp"] + VISION_ABBR

AESTHETIC_DIMS = [
    "subject_moment",
    "composition",
    "lighting",
    "color",
    "depth_separation",
    "mood_story",
]

AESTHETIC_SOURCE_MAP = {
    "subject_moment": "subject",
    "composition": "composition",
    "lighting": "lighting",
    "color": "color",
    "depth_separation": "depth",
    "mood_story": "mood",
}

VISIBLE_BREAKDOWN_DIMS = [
    "technical_quality",
    "composition",
    "lighting",
    "color",
    "space_depth",
    "mood_story",
    "subject_moment",
]

SIGNAL_STAGES = ["group", "technical", "screening", "aesthetic", "aggregate"]

DIM_LABELS_CN = {
    "exposure": "曝光",
    "sharpness": "锐度",
    "subject": "主体",
    "subject_moment": "关键瞬间",
    "composition": "构图",
    "lighting": "光线",
    "color": "色彩",
    "clarity": "清晰",
    "depth": "层次",
    "depth_separation": "空间层次",
    "mood": "氛围",
    "mood_story": "氛围",
    "technical_quality": "技术质量",
    "subject_focus": "主体对焦",
    "space_depth": "空间层次",
    "portrait_face_eye_usability": "人物可用性",
}

DIM_LABELS_EN = {
    "exposure": "Exposure",
    "sharpness": "Sharpness",
    "subject": "Subject",
    "subject_moment": "Subject Moment",
    "composition": "Composition",
    "lighting": "Lighting",
    "color": "Color",
    "clarity": "Clarity",
    "depth": "Depth",
    "depth_separation": "Depth Separation",
    "mood": "Mood",
    "mood_story": "Mood Story",
    "technical_quality": "Technical Quality",
    "subject_focus": "Subject Focus",
    "space_depth": "Space Depth",
    "portrait_face_eye_usability": "Portrait Face/Eye Usability",
}


def scene_label(scene: str, output_language: str = "zh") -> str:
    canonical = LEGACY_SCENE_MIGRATIONS.get(scene, scene)
    if output_language == "en":
        return SCENE_LABELS_EN.get(canonical, SCENE_LABELS_EN["other"])
    return SCENE_LABELS.get(canonical, SCENE_LABELS["other"])


def dim_label(dim: str, output_language: str = "zh") -> str:
    if output_language == "en":
        return DIM_LABELS_EN.get(dim, dim)
    return DIM_LABELS_CN.get(dim, dim)


def scene_key_from_display(value: str) -> str:
    normalized = value.strip()
    key = _DISPLAY_ALIASES.get(normalized)
    if key is None:
        key = _LEGACY_KEY_LOWER_TO_NEW.get(normalized.lower())
    if key is None:
        raise KeyError(value)
    return key


def is_scene_label(value: str) -> bool:
    normalized = value.strip()
    return (
        normalized.lower() in _SCENE_KEY_LOWER_SET
        or normalized.lower() in _LEGACY_KEY_LOWER_TO_NEW
        or normalized in SCENE_LABEL_TO_KEY
    )
