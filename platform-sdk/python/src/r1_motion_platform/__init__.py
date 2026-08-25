"""Public teaching-platform client; this package has no robot or DDS API."""

from r1_motion_platform.client import SimulationClient
from r1_motion_platform.package import build_motion_package

__all__ = ["SimulationClient", "build_motion_package"]
