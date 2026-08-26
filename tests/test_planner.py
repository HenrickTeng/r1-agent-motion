import pytest

from r1_agent.asr import select_transcript
from r1_agent.executor import Executor, SimulatedBackend
from r1_agent.planner import DeepSeekPlanner, RulePlanner


def test_plans_serial_walk_then_arm():
    _, actions = RulePlanner().plan("请向前走一步，然后向左转，再挥右手")
    assert [action.name for action in actions] == ["move_forward_slow", "turn_left_10", "wave_right"]
    backend = SimulatedBackend()
    Executor(backend).execute(actions)
    assert backend.events == [
        "MOVE move_forward_slow {'vx': 0.05, 'vy': 0.0, 'omega': 0.0, 'duration': 0.5}",
        "STOP",
        "TURN turn_left_10 {'vx': 0.0, 'vy': 0.0, 'omega': 0.35, 'duration': 0.5}",
        "STOP",
        "ARM wave_right",
        "STOP",
    ]


def test_longest_alias_wins_for_twenty_degree_turn():
    _, actions = RulePlanner().plan("向左转二十度")
    assert [action.name for action in actions] == ["turn_left_20"]


def test_rejects_unsafe_motion():
    reply, actions = RulePlanner().plan("跳舞然后鞠躬")
    assert actions == []
    assert "不会执行" in reply


def test_self_intro_and_salute():
    _, actions = RulePlanner().plan("请介绍自己，然后敬礼")
    assert [action.name for action in actions] == ["self_intro", "salute_right"]


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


def test_asr_accepts_latest_meaningful_non_final_message():
    output = "\n".join([
        '{"text":"。","confidence":0.9,"is_final":false}',
        '{"text":"你好你好。","confidence":0.5,"is_final":false}',
    ])
    assert select_transcript(output)["text"] == "你好你好。"


def test_asr_rejects_low_confidence_and_no_speech():
    with pytest.raises(ValueError):
        select_transcript('{"text":"<|nospeech|>","confidence":0.9}\n{"text":"你好","confidence":0.2}')
