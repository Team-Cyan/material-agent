import sqlite3
from argparse import Namespace

import pytest

from material_agent.commands.db import cmd_remap_scenes, cmd_scan_scenes, cmd_suggest_scenes
from material_agent.commands.io import cmd_rewrite_commentary, cmd_rewrite_xmp
from material_agent.clients.ollama import parse_vision_response
from material_agent.utils.constants import (
    LEGACY_SCENE_MIGRATIONS,
    SCENE_LABELS,
    SCENE_LIST,
    scene_key_from_display,
    scene_label,
)
from material_agent.utils.runtime_paths import build_runtime_paths


def _make_db(tmp_path):
    db_path = build_runtime_paths(tmp_path).db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS processed (
                file_path TEXT PRIMARY KEY,
                status TEXT,
                scene TEXT,
                scene_raw TEXT,
                total_score REAL,
                star_rating INTEGER,
                group_rank INTEGER,
                group_size INTEGER,
                group_boosted INTEGER,
                group_id TEXT,
                score_exposure REAL,
                score_sharpness REAL,
                score_subject REAL,
                score_composition REAL,
                score_lighting REAL,
                score_color REAL,
                score_clarity REAL,
                score_depth REAL,
                score_mood REAL,
                commentary_group_issues TEXT,
                commentary_shooting TEXT,
                commentary_post TEXT
            );
            """
        )
        conn.commit()
    return db_path


def test_scene_constants_use_new_canonical_keys():
    assert SCENE_LIST == [
        "people",
        "sports",
        "landscape",
        "city",
        "indoor",
        "detail",
        "animals",
        "other",
    ]
    assert SCENE_LABELS["people"] == "人物"
    assert SCENE_LABELS["detail"] == "特写"
    assert scene_label("animals") == "动物"
    assert scene_key_from_display("城市") == "city"


def test_legacy_scene_migrations_use_two_phase_defaults():
    assert LEGACY_SCENE_MIGRATIONS["concert"] == "people"
    assert LEGACY_SCENE_MIGRATIONS["food"] == "detail"
    assert LEGACY_SCENE_MIGRATIONS["wildlife"] == "animals"
    assert LEGACY_SCENE_MIGRATIONS["street"] == "other"
    assert LEGACY_SCENE_MIGRATIONS["travel"] == "other"


def test_parse_vision_response_accepts_new_scene_and_chinese_scene_raw():
    raw = (
        '{"scene":"people","scene_raw":"舞台上的主唱特写","subject":8.0,'
        '"composition":7.0,"lighting":7.0,"color":6.0,"clarity":6.5,"depth":4.0,"mood":5.0}'
    )
    result = parse_vision_response(raw)
    assert result["scene"] == "people"
    assert result["scene_raw"] == "舞台上的主唱特写"


def test_parse_vision_response_invalid_old_scene_falls_back_to_other():
    raw = (
        '{"scene":"concert","scene_raw":"舞台上的主唱特写","subject":8.0,'
        '"composition":7.0,"lighting":7.0,"color":6.0,"clarity":6.5,"depth":4.0,"mood":5.0}'
    )
    result = parse_vision_response(raw)
    assert result["scene"] == "other"


def test_parse_vision_response_clears_scene_raw_when_it_is_a_chinese_label():
    raw = (
        '{"scene":"people","scene_raw":"人物","subject":8.0,'
        '"composition":7.0,"lighting":7.0,"color":6.0,"clarity":6.5,"depth":4.0,"mood":5.0}'
    )
    result = parse_vision_response(raw)
    assert result["scene_raw"] == ""


def test_cmd_remap_scenes_accepts_chinese_target_and_writes_english_key(tmp_path, capsys):
    db_path = _make_db(tmp_path)
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            "INSERT INTO processed (file_path, status, scene, scene_raw) VALUES (?,?,?,?)",
            [
                ("/a.arw", "done", "other", "猫趴在窗边"),
                ("/b.arw", "done", "other", "猫趴在窗边"),
            ],
        )
        conn.commit()

    cmd_remap_scenes(Namespace(dir=str(tmp_path), from_="猫趴在窗边", to="动物"))
    out = capsys.readouterr().out
    assert "2" in out

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT scene FROM processed WHERE scene_raw='猫趴在窗边'"
        ).fetchall()
    assert all(row[0] == "animals" for row in rows)


def test_cmd_scan_scenes_displays_chinese_scene_labels(tmp_path, capsys):
    db_path = _make_db(tmp_path)
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            "INSERT INTO processed (file_path, status, scene, scene_raw) VALUES (?,?,?,?)",
            [
                ("/a.arw", "done", "people", "舞台上的主唱特写"),
                ("/b.arw", "done", "people", "舞台上的吉他手"),
                ("/c.arw", "done", "city", "雨夜街头"),
            ],
        )
        conn.commit()

    cmd_scan_scenes(Namespace(dir=str(tmp_path)))
    out = capsys.readouterr().out
    assert "[people]" in out
    assert "[city]" in out
    assert "舞台上的主唱特写" in out


def test_cmd_suggest_scenes_only_scans_other_and_shows_chinese_suggestions(tmp_path, capsys):
    db_path = _make_db(tmp_path)
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            "INSERT INTO processed (file_path, status, scene, scene_raw) VALUES (?,?,?,?)",
            [
                ("/a.arw", "done", "other", "猫趴在窗边"),
                ("/b.arw", "done", "other", "猫趴在窗边"),
                ("/c.arw", "done", "other", "夜晚城市街景"),
                ("/d.arw", "done", "people", "舞台上的主唱特写"),
            ],
        )
        conn.commit()

    cmd_suggest_scenes(Namespace(dir=str(tmp_path), limit=20, min_count=1))
    out = capsys.readouterr().out
    assert "猫趴在窗边" in out
    assert "animals" in out
    assert "夜晚城市街景" in out
    assert "city" in out
    assert "舞台上的主唱特写" not in out


def test_rewrite_xmp_writes_chinese_scene_tag_from_english_db_value(tmp_path):
    _make_db(tmp_path)
    photo = tmp_path / "cat.ARW"
    photo.write_bytes(b"raw")
    with sqlite3.connect(build_runtime_paths(tmp_path).db_path) as conn:
        conn.execute(
            """
            INSERT INTO processed (
                file_path, status, scene, scene_raw, total_score, star_rating,
                group_rank, group_size, group_boosted, group_id,
                score_exposure, score_sharpness, score_subject, score_composition,
                score_lighting, score_color, score_clarity, score_depth, score_mood
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                str(photo), "done", "animals", "猫趴在窗边", 8.0, 4,
                1, 1, 0, "group_1",
                8.0, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0,
            ),
        )
        conn.commit()

    cmd_rewrite_xmp(Namespace(dir=str(tmp_path), dry_run=False))
    xmp = tmp_path / "cat.xmp"
    content = xmp.read_text(encoding="utf-8")
    assert "pj:scene=动物" in content
    assert "pj:scene=animals" not in content


def test_rewrite_commentary_repairs_done_rows_and_optionally_rewrites_xmp(tmp_path):
    _make_db(tmp_path)
    photo1 = tmp_path / "a.ARW"
    photo2 = tmp_path / "b.ARW"
    photo1.write_bytes(b"raw")
    photo2.write_bytes(b"raw")
    with sqlite3.connect(build_runtime_paths(tmp_path).db_path) as conn:
        conn.executemany(
            """
            INSERT INTO processed (
                file_path, status, scene, scene_raw, total_score, star_rating,
                group_rank, group_size, group_boosted, group_id,
                score_exposure, score_sharpness, score_subject, score_composition,
                score_lighting, score_color, score_clarity, score_depth, score_mood,
                commentary_group_issues, commentary_shooting, commentary_post
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            [
                (
                    str(photo1), "done", "people", "舞台上的表演者", 6.4, 3,
                    1, 2, 0, "group_1",
                    6.0, 5.8, 7.0, 6.2, 6.1, 5.0, 4.0, 5.2, 5.8,
                    "【组内问题】旧问题", "【拍摄建议】提升锐度与色彩饱和度，确保主体清晰。", "【后期指导】下次拍摄时应适当增加曝光值。",
                ),
                (
                    str(photo2), "done", "people", "舞台上的表演者", 6.1, 3,
                    2, 2, 0, "group_1",
                    5.9, 5.7, 6.8, 6.0, 6.0, 5.2, 4.3, 5.0, 5.6,
                    "【组内问题】旧问题", "【拍摄建议】提升锐度与色彩饱和度，确保主体清晰。", "【后期指导】下次拍摄时应适当增加曝光值。",
                ),
            ],
        )
        conn.commit()

    cmd_rewrite_commentary(
        Namespace(dir=str(tmp_path), config="config.yaml", dry_run=False, rewrite_xmp=True)
    )

    with sqlite3.connect(build_runtime_paths(tmp_path).db_path) as conn:
        rows = conn.execute(
            "SELECT commentary_group_issues, commentary_shooting, commentary_post FROM processed ORDER BY file_path"
        ).fetchall()

    assert rows[0][0].startswith("【组内问题】这组")
    assert "拍摄时优先把快门再提一点并稳住机位" in rows[0][1]
    assert rows[0][2].startswith("【后期指导】")
    assert "清晰和色彩" in rows[0][2]
    assert "舞台状态" in rows[0][2]
    assert "下次拍摄时" not in rows[0][2]

    xmp = photo1.with_suffix(".xmp")
    content = xmp.read_text(encoding="utf-8")
    assert "【组内问题】这组" in content
    assert "【后期指导】" in content
    assert "清晰和色彩" in content


def test_scene_key_from_display_rejects_unknown_label():
    with pytest.raises(KeyError):
        scene_key_from_display("不存在")
