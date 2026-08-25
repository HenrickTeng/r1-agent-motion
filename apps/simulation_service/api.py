"""Synchronous reference API; production workers can preserve the same contract."""

from pathlib import Path

from fastapi import FastAPI, HTTPException

from motion_core.compiler import MotionCompiler
from motion_core.config import PROJECT_ROOT, Settings
from motion_core.errors import R1MotionError
from motion_core.schemas import CompiledTrajectory, MotionDesignSpec
from motion_core.simulator import TrajectorySimulator


def create_app() -> FastAPI:
    settings = Settings.from_env()
    compiler = MotionCompiler(PROJECT_ROOT / "config" / "classroom-upper-v1.json")
    model_xml = settings.unitree_r1_model_dir / "r1.xml" if settings.unitree_r1_model_dir else None
    simulator = TrajectorySimulator(model_xml)
    reports: dict[str, dict] = {}
    previews: dict[str, dict] = {}
    app = FastAPI(title="R1 MuJoCo Simulation Service", version="1.0.0")

    @app.post("/v1/compile")
    def compile_motion(payload: dict) -> dict:
        try:
            spec = MotionDesignSpec.model_validate(payload)
            return compiler.compile(spec).model_dump(mode="json")
        except (R1MotionError, ValueError) as error:
            raise HTTPException(422, str(error)) from error

    @app.post("/v1/simulations")
    def create_simulation(payload: dict) -> dict:
        try:
            trajectory = CompiledTrajectory.model_validate(payload)
            report = simulator.run(trajectory)
        except (R1MotionError, ValueError) as error:
            raise HTTPException(422, str(error)) from error
        reports[report.simulation_id] = report.model_dump(mode="json")
        previews[report.simulation_id] = {
            "schema_version": "preview-animation/v1",
            "trajectory_sha256": trajectory.trajectory_sha256,
            "joint_order": list(trajectory.joint_order),
            "frames": [
                {"time_s": sample.time_s, "position_rad": list(sample.position_rad)}
                for sample in trajectory.samples[::5]
            ],
        }
        return {"simulation_id": report.simulation_id, "status": "completed", "passed": report.passed}

    @app.get("/v1/simulations/{simulation_id}")
    def get_simulation(simulation_id: str) -> dict:
        if simulation_id not in reports:
            raise HTTPException(404, "simulation not found")
        return {"simulation_id": simulation_id, "status": "completed", "passed": reports[simulation_id]["passed"]}

    @app.get("/v1/simulations/{simulation_id}/report")
    def get_report(simulation_id: str) -> dict:
        if simulation_id not in reports:
            raise HTTPException(404, "simulation not found")
        return reports[simulation_id]

    @app.get("/v1/simulations/{simulation_id}/preview")
    def get_preview(simulation_id: str) -> dict:
        if simulation_id not in previews:
            raise HTTPException(404, "simulation not found")
        return previews[simulation_id]

    return app


app = create_app()
