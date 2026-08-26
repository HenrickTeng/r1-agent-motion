from motion_core.demo import DemoExecutor, DemoPlanner, SimulatedBackend

def test_plans_serial_walk_then_arm():
    reply, actions = DemoPlanner().plan("请向前走一步，然后向左转，再挥右手")
    assert [a.name for a in actions] == ["move_forward_slow", "turn_left_10", "wave_right"]
    backend = SimulatedBackend()
    DemoExecutor(backend).execute(actions)
    assert backend.events == ["MOVE move_forward_slow {'vx': 0.05, 'vy': 0.0, 'duration': 0.5}", "STOP", "TURN turn_left_10 {'angle_deg': 10.0}", "STOP", "ARM wave_right", "STOP"]

def test_rejects_unsafe_motion():
    reply, actions = DemoPlanner().plan("跳舞然后跑步")
    assert actions == []
    assert "不会执行" in reply
