"""Stable error codes shared by CLI and services."""


class R1MotionError(Exception):
    code = "R1_INTERNAL"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "details": self.details}


class ContractError(R1MotionError):
    code = "R1_CONTRACT_INVALID"


class SafetyError(R1MotionError):
    code = "R1_SAFETY_REJECTED"


class ApprovalError(R1MotionError):
    code = "R1_APPROVAL_REQUIRED"


class GatewayUnavailable(R1MotionError):
    code = "R1_GATEWAY_UNAVAILABLE"
