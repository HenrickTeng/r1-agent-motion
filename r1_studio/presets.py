PRESETS = [
    {
        "id": "step_forward",
        "title": "前进一步",
        "hint": "与语音「向前走」相同：0.5m/s × 0.5s",
        "steps": ["move_forward_slow"],
    },
    {
        "id": "step_back",
        "title": "后退一步",
        "hint": "与语音「向后」相同",
        "steps": ["move_backward_slow"],
    },
    {
        "id": "step_left",
        "title": "左移一步",
        "hint": "横移 0.5m/s × 1s（0.2 只会倾身）",
        "steps": ["move_left_slow"],
    },
    {
        "id": "step_right",
        "title": "右移一步",
        "hint": "横移 -0.5m/s × 1s",
        "steps": ["move_right_slow"],
    },
    {
        "id": "welcome",
        "title": "欢迎来宾",
        "hint": "张开双臂 + 挥手",
        "steps": ["open_arms", "wave_right"],
    },
    {
        "id": "class_start",
        "title": "开始上课",
        "hint": "问好并挥手复位",
        "steps": ["say:lesson_start", "open_arms", "wave_right", "ready_pose"],
    },
    {
        "id": "praise",
        "title": "表扬回答",
        "hint": "点头 + 鼓励",
        "steps": ["nod", "small_cheer", "say:praise"],
    },
    {
        "id": "cheer",
        "title": "欢呼比耶",
        "hint": "双手举起再鼓掌",
        "steps": ["cheer_both", "clap"],
    },
    {
        "id": "look_around",
        "title": "左右看看",
        "hint": "转头环顾",
        "steps": ["look", "look_right", "ready_pose"],
    },
    {
        "id": "invite",
        "title": "邀请举手",
        "hint": "请同学回答",
        "steps": ["say:invite_answer", "raise_hand_right"],
    },
]
