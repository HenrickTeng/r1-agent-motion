"""Environment-backed configuration with safe local defaults."""

from dataclasses import dataclass
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    unitree_sdk2_dir: Path | None
    unitree_r1_model_dir: Path | None
    database_url: str
    gateway_target: str
    network_interface: str
    teacher_bridge_host: str = "127.0.0.1"
    teacher_bridge_port: int = 8765

    @classmethod
    def from_env(cls) -> "Settings":
        sdk = os.getenv("UNITREE_SDK2_DIR")
        model = os.getenv("UNITREE_R1_MODEL_DIR")
        return cls(
            unitree_sdk2_dir=Path(sdk).expanduser().resolve() if sdk else None,
            unitree_r1_model_dir=Path(model).expanduser().resolve() if model else None,
            database_url=os.getenv(
                "R1_DATABASE_URL", f"sqlite:///{PROJECT_ROOT / 'r1-motion.sqlite3'}"
            ),
            gateway_target=os.getenv("R1_GATEWAY_TARGET", "192.168.123.164:50051"),
            network_interface=os.getenv("R1_NETWORK_INTERFACE", "enp7s0"),
        )
