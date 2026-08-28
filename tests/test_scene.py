import json

import pytest

from r1_agent.catalog import ROOT, load_catalog, load_scene_pack, merge_scene
from r1_agent.planner import DeepSeekPlanner, RulePlanner


def _write_scene(tmp_path, *, context="", pack=None):
    if context:
        (tmp_path / "context.txt").write_text(context, encoding="utf-8")
    if pack is not None:
        (tmp_path / "pack.json").write_text(json.dumps(pack, ensure_ascii=False), encoding="utf-8")
    return tmp_path


def test_example_classroom_scene_loads():
    pack = load_scene_pack(ROOT / "scenes" / "classroom")
    catalog = merge_scene(load_catalog(), pack)
    planner = RulePlanner(catalog)
    assert "课堂助手" in pack.context
    assert catalog.prompt_compositions["欢迎来宾"] == ["open_arms", "wave_right"]
    assert catalog.prompt_compositions["校长来了"] == ["open_arms", "wave_right"]
    _, backward = planner.plan("后短信")
    assert [action.name for action in backward] == ["move_backward_slow"]
    _, welcome = planner.plan("校长来了")
    assert [action.name for action in welcome] == ["open_arms", "wave_right"]


def test_scene_rejects_unknown_atoms(tmp_path):
    _write_scene(tmp_path, pack={"compositions": {"飞天": ["dance"]}})
    with pytest.raises(ValueError, match="unknown atoms"):
        merge_scene(load_catalog(), load_scene_pack(tmp_path))


def test_scene_rejects_unknown_alias_target(tmp_path):
    _write_scene(tmp_path, pack={"aliases": {"跳一下": "dance"}})
    with pytest.raises(ValueError, match="unknown name"):
        merge_scene(load_catalog(), load_scene_pack(tmp_path))


def test_scene_speech_and_context_reach_planners(tmp_path, monkeypatch):
    _write_scene(
        tmp_path,
        context="你是迎宾机器人。",
        pack={
            "speech": {"greeting": "欢迎参观。"},
            "compositions": {"开场": ["say:greeting", "wave_right"]},
        },
    )
    pack = load_scene_pack(tmp_path)
    catalog = merge_scene(load_catalog(), pack)
    _, actions = RulePlanner(catalog).plan("开场")
    assert [action.name for action in actions] == ["say:greeting", "wave_right"]
    assert actions[0].args["text"] == "欢迎参观。"

    captured = {}
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return '{"choices":[{"message":{"content":"{\\"reply\\":\\"ok\\",\\"actions\\":[\\"开场\\"]}"}}]}'.encode()

    def fake_open(req, timeout=None):
        captured["system"] = json.loads(req.data.decode())["messages"][0]["content"]
        return FakeResponse()

    monkeypatch.setattr("r1_agent.planner.request.urlopen", fake_open)
    planner = DeepSeekPlanner(catalog, context=pack.context)
    _, planned = planner.plan("请开场")
    assert [action.name for action in planned] == ["say:greeting", "wave_right"]
    assert "开场" in captured["system"]
    assert "你是迎宾机器人。" in captured["system"]
    assert "后短信" not in captured["system"]
