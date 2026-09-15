from imitate.joints import ARM_JOINTS
from imitate.sequence import iter_motion_poses, parse_sequence, pose_from_abs13, ready_arm_pose, run_edit_sequence
from r1_agent.dds_robot import MOTIONS
from r1_studio.programs import ProgramError


def test_parse_sequence_accepts_arm_atoms():
    assert parse_sequence("wave_right, cheer_both, nod") == ["wave_right", "cheer_both", "nod"]


def test_parse_sequence_rejects_walk():
    try:
        parse_sequence("move_forward_slow")
        assert False
    except ProgramError:
        pass


def test_motion_poses_start_and_end_at_ready():
    ready = ready_arm_pose()
    frames = list(iter_motion_poses("cheer_both", dt=0.2))
    assert len(frames) > 5
    assert set(frames[0]) == set(ARM_JOINTS)
    assert frames[0]["left_shoulder_pitch"] == ready["left_shoulder_pitch"]
    last = pose_from_abs13(MOTIONS["cheer_both"][-1][1])
    assert last["left_shoulder_pitch"] != ready["left_shoulder_pitch"]


def test_headless_play_sequence():
    assert run_edit_sequence(play="wave_right,nod", headless=True) == 0
