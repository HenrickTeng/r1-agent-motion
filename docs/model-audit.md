# `r1-edu-26dof-v1` model audit

The observed external model is `/home/henrick/unitree_rl_mjlab/src/assets/robots/unitree_r1/xmls/r1.xml`, SHA256 `19c2291ce675217cc193092e59726bbd8d21c53bd5b2599912b60fe538f2de5f`. Its redistribution license was not found, so this repository references it through `UNITREE_R1_MODEL_DIR` and does not copy model or mesh assets.

The audit loader confirms the model can be parsed only after ignoring two exclusions that reference nonexistent `left_wrist_pitch_link` and `right_wrist_pitch_link` bodies. It exposes articulated arm and `waist_yaw` joints, but the visible head meshes are fixed to the torso and `head_pitch_joint`/`head_yaw_joint` are absent. It also includes `waist_roll_joint`, which is not in the 13-joint ArmSdk command order.

Simulation reports therefore fail `all_armsdk_joints_mapped` and `invalid_contact_exclusions`. This is an intentional release gate, not a warning to suppress. A licensed corrected model, complete 35→26→13 mapping, actuator mapping, foot-ground setup and dynamics thresholds are required before `local_simulation_passed` or `v0.2.0-motion-foundry` can represent an authoritative motion foundry.
