import json

import pytest

from r1_agent.asr import select_transcript
from r1_agent.cli import _planner
from r1_agent.executor import Executor, SimulatedBackend
from r1_agent.planner import DeepSeekPlanner, RulePlanner, load_deepseek_key


def test_listen_defaults_to_deepseek_planner():
    assert isinstance(_planner(listen=True, deepseek=False), DeepSeekPlanner)
    assert isinstance(_planner(listen=False, deepseek=False), RulePlanner)
    assert isinstance(_planner(listen=False, deepseek=True), DeepSeekPlanner)


def test_plans_walk_and_arm_together():
    _, actions = RulePlanner().plan("请向前走一步，然后向左转，再挥右手")
    assert [action.name for action in actions] == ["move_forward_slow", "turn_left_10", "wave_right"]
    backend = SimulatedBackend()
    Executor(backend).execute(actions)
    kinds = [event.split()[0] + (" " + event.split()[1] if event.split()[0] in {"MOVE", "TURN", "ARM"} else "") for event in backend.events]
    assert "MOVE move_forward_slow" in kinds
    assert "TURN turn_left_10" in kinds
    assert "ARM wave_right" in kinds
    assert kinds[-1] == "STOP"


def test_longest_alias_wins_for_twenty_degree_turn():
    _, actions = RulePlanner().plan("向左转二十度")
    assert [action.name for action in actions] == ["turn_left_20"]


def test_loco_aliases_and_waist():
    _, actions = RulePlanner().plan("向前走两步然后向左转四十五度再停下")
    assert [action.name for action in actions] == ["move_forward_long", "turn_left_45", "stop_move"]
    _, ninety = RulePlanner().plan("左转90度")
    assert [action.name for action in ninety] == ["turn_left_90"]
    _, waist = RulePlanner().plan("向左转腰")
    assert [action.name for action in waist] == ["waist_left"]


def test_rejects_unsafe_motion():
    reply, actions = RulePlanner().plan("跳舞然后鞠躬")
    assert actions == []
    assert "不会执行" in reply


def test_self_intro_and_salute():
    _, actions = RulePlanner().plan("请介绍自己，然后敬礼")
    assert [action.name for action in actions] == ["self_intro", "salute_right"]


def test_peace_cheer_alias():
    _, actions = RulePlanner().plan("请比耶欢呼")
    assert [action.name for action in actions] == ["cheer_both"]


def test_extract_message_text_prefers_content_then_reasoning():
    from r1_agent.planner import extract_message_text

    assert extract_message_text({"content": " 连通 "}) == "连通"
    assert extract_message_text({"content": "", "reasoning_content": "连通"}) == "连通"
    assert extract_message_text({"content": [{"type": "text", "text": "连通"}]}) == "连通"


def test_probe_llm_rejects_placeholder(monkeypatch):
    from r1_studio.probe import probe_llm

    monkeypatch.setenv("DEEPSEEK_API_KEY", "公司给你的 key")
    assert probe_llm() == 1


def test_deepseek_key_file_used_when_env_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    path = tmp_path / "deepseek_key.txt"
    path.write_text("sk-from-file\n", encoding="utf-8")
    assert load_deepseek_key(path) == "sk-from-file"
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-from-env")
    assert load_deepseek_key(path) == "sk-from-env"


def test_deepseek_rejects_unknown_action_names(monkeypatch):
    planner = DeepSeekPlanner()
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b'{"choices":[{"message":{"content":"{\\"reply\\":\\"ok\\",\\"actions\\":[\\"dance\\"]}"}}]}'

    monkeypatch.setattr("r1_agent.planner.request.urlopen", lambda *args, **kwargs: FakeResponse())
    reply, actions = planner.plan("挥挥手")
    assert actions == []
    assert "不会执行" in reply
    assert planner._turns[0]["content"] == "挥挥手"
    assert "dance" not in planner._turns[1]["content"]


def test_deepseek_runs_composed_atom_sequence(monkeypatch):
    planner = DeepSeekPlanner()
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b'{"choices":[{"message":{"content":"{\\"reply\\":\\"ok\\",\\"actions\\":[\\"wave_right\\",\\"nod\\",\\"clap\\"]}"}}]}'

    monkeypatch.setattr("r1_agent.planner.request.urlopen", lambda *args, **kwargs: FakeResponse())
    _, actions = planner.plan("请按你的理解回应这个情境")
    assert [action.name for action in actions] == ["wave_right", "nod", "clap"]


def test_deepseek_prompt_is_general_composition(monkeypatch):
    planner = DeepSeekPlanner()
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b'{"choices":[{"message":{"content":"{\\"reply\\":\\"ok\\",\\"actions\\":[\\"wave_right\\"]}"}}]}'

    def fake_open(req, timeout=None):
        captured["system"] = json.loads(req.data.decode())["messages"][0]["content"]
        return FakeResponse()

    monkeypatch.setattr("r1_agent.planner.request.urlopen", fake_open)
    planner.plan("随便说点什么")
    assert "原子动作" in captured["system"]
    assert "ASR" in captured["system"]
    assert "aliases" in captured["system"]
    assert "wave_right" in captured["system"]
    assert "wrist_wave" in captured["system"]
    assert "不要为某个场景写死套路" in captured["system"]
    assert "迎宾可用" not in captured["system"]
    assert "同时执行" in captured["system"]
    assert "必须串行" not in captured["system"]
    assert "已设定的角色" in captured["system"]


def test_deepseek_keeps_context_across_turns(monkeypatch):
    planner = DeepSeekPlanner()
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    seen: list[list] = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b'{"choices":[{"message":{"content":"{\\"reply\\":\\"ok\\",\\"actions\\":[\\"wave_right\\"]}"}}]}'

    def fake_open(req, timeout=None):
        seen.append(json.loads(req.data.decode())["messages"])
        return FakeResponse()

    monkeypatch.setattr("r1_agent.planner.request.urlopen", fake_open)
    planner.plan("先记住你现在是课堂助手")
    planner.plan("请按刚才的角色继续")
    assert seen[1][1]["content"] == "先记住你现在是课堂助手"
    assert seen[1][-1]["content"] == "请按刚才的角色继续"


def test_deepseek_keeps_role_after_unclear_asr(monkeypatch):
    planner = DeepSeekPlanner()
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    replies = [
        '{"choices":[{"message":{"content":"{\\"reply\\":\\"我是校园机器人\\",\\"actions\\":[\\"self_intro\\"]}"}}]}'.encode(),
        '{"choices":[{"message":{"content":"{\\"reply\\":\\"抱歉，我没听清您的意思，请再说一遍好吗？\\",\\"actions\\":[]}"}}]}'.encode(),
        '{"choices":[{"message":{"content":"{\\"reply\\":\\"欢迎\\",\\"actions\\":[\\"wave_right\\"]}"}}]}'.encode(),
    ]
    seen: list[list] = []

    class FakeResponse:
        def __init__(self, payload: bytes) -> None:
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return self.payload

    def fake_open(req, timeout=None):
        seen.append(json.loads(req.data.decode())["messages"])
        return FakeResponse(replies.pop(0))

    monkeypatch.setattr("r1_agent.planner.request.urlopen", fake_open)
    planner.plan("你现在是校园迎宾机器人")
    planner.plan("是管我们个个业绩。")
    planner.plan("请过来迎接我")
    contents = [message["content"] for message in seen[2]]
    assert "你现在是校园迎宾机器人" in contents
    assert "是管我们个个业绩。" not in contents
    assert planner._turns[-1]["content"] == '{"reply": "欢迎", "actions": ["wave_right"]}' or "wave_right" in planner._turns[-1]["content"]


def test_asr_prefers_final_over_later_partial():
    output = "\n".join([
        '{"text":"挥右手。","confidence":0.7,"is_final":true}',
        '{"text":"右手。","confidence":0.9,"is_final":false}',
    ])
    assert select_transcript(output)["text"] == "挥右手。"


def test_asr_accepts_latest_meaningful_non_final_message():
    output = "\n".join([
        '{"text":"。","confidence":0.9,"is_final":false}',
        '{"text":"你好你好。","confidence":0.5,"is_final":false}',
    ])
    assert select_transcript(output)["text"] == "你好你好。"


def test_asr_rejects_low_confidence_and_no_speech():
    with pytest.raises(ValueError):
        select_transcript('{"text":"<|nospeech|>","confidence":0.9}\n{"text":"你好","confidence":0.2}')


def test_asr_rejects_non_chinese_noise():
    with pytest.raises(ValueError):
        select_transcript('{"text":" 그片.","confidence":0.9,"is_final":false}')


def test_classroom_aliases_and_new_gestures():
    _, actions = RulePlanner().plan("打招呼然后鼓掌再加油")
    assert [action.name for action in actions] == ["wave_right", "clap", "small_cheer"]


def test_look_right_then_come_here():
    _, actions = RulePlanner().plan("向右看然后过来")
    assert [action.name for action in actions] == ["look_right", "come_here"]


def test_right_hand_alias_is_full_wave():
    _, actions = RulePlanner().plan("右手")
    assert [action.name for action in actions] == ["wave_right"]


def test_wave_hand_alias_is_wave_right():
    _, actions = RulePlanner().plan("挥手")
    assert [action.name for action in actions] == ["wave_right"]


def test_right_hand_salute_still_wins():
    _, actions = RulePlanner().plan("右手敬礼")
    assert [action.name for action in actions] == ["salute_right"]


def test_longest_alias_keeps_left_wave():
    _, actions = RulePlanner().plan("挥左手")
    assert [action.name for action in actions] == ["wave_left"]
