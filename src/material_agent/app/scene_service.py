from contextlib import nullcontext

from ..adapters.state.processed_sqlite import SQLiteProcessedRepository

from ..utils.constants import SCENE_LIST, scene_key_from_display

_SUGGESTION_KEYWORDS = {
    "animals": ["猫", "狗", "鸟", "宠物", "小狗", "小猫", "飞鸟", "动物"],
    "city": ["城市", "街头", "街景", "霓虹", "夜景", "楼", "建筑", "路口"],
    "landscape": ["山", "海", "日落", "日出", "湖", "草原", "云海", "风光"],
    "indoor": ["室内", "房间", "客厅", "咖啡馆", "餐厅", "展馆", "书店"],
    "detail": ["特写", "细节", "近景", "食物", "咖啡", "甜点", "寿司", "花"],
    "people": ["人物", "人像", "主唱", "歌手", "吉他手", "观众", "男孩", "女孩", "人"],
    "sports": ["跑步", "比赛", "足球", "篮球", "运动", "冲刺", "骑行"],
}


class SceneDbService:
    def __init__(self, repository: SQLiteProcessedRepository | None = None):
        self.repository = repository

    def scan_distribution(self, input_dir: str) -> dict[str, list[tuple[str, int]]]:
        with self._open_repository(input_dir) as repository:
            return repository.scan_distribution()

    def remap_scene(self, input_dir: str, *, from_raw: str, to_display: str) -> tuple[str, int]:
        target_scene = scene_key_from_display(to_display)
        if target_scene not in set(SCENE_LIST):
            raise KeyError(to_display)
        with self._open_repository(input_dir) as repository:
            count = repository.remap_scene(from_raw=from_raw, to_scene=target_scene)
        return target_scene, count

    def suggest_scenes(self, input_dir: str, *, limit: int, min_count: int) -> list[tuple[str, int, str]]:
        suggestions = []
        with self._open_repository(input_dir) as repository:
            rows = repository.suggest_scene_raws(limit=limit, min_count=min_count)
        for scene_raw, cnt in rows:
            suggested_scene = self._suggest_scene_for_raw(scene_raw)
            if suggested_scene is None:
                continue
            suggestions.append((scene_raw, cnt, suggested_scene))
        return suggestions

    def fix_db(self, input_dir: str) -> dict[str, int]:
        with self._open_repository(input_dir) as repository:
            return repository.fix_db()

    @staticmethod
    def _suggest_scene_for_raw(scene_raw: str) -> str | None:
        for scene, keywords in _SUGGESTION_KEYWORDS.items():
            if any(keyword in scene_raw for keyword in keywords):
                return scene
        return None

    def _open_repository(self, input_dir: str):
        if self.repository is not None:
            return nullcontext(self.repository)
        return SQLiteProcessedRepository(input_dir)
