"""Strict model outputs; all LLM content remains untrusted."""

from typing import Literal

from pydantic import Field, model_validator

from motion_core.schemas.models import MotionDesignSpec, MotionPlan, StrictModel


class AgentResponse(StrictModel):
    reply: str = Field(min_length=1, max_length=240)
    intent: Literal["conversation", "execute_motion", "design_motion"]
    plan: MotionPlan | None = None
    design: MotionDesignSpec | None = None

    @model_validator(mode="after")
    def payload_matches_intent(self) -> "AgentResponse":
        if self.intent == "execute_motion" and (self.plan is None or self.design is not None):
            raise ValueError("execute_motion requires only a MotionPlan")
        if self.intent == "design_motion" and (self.design is None or self.plan is not None):
            raise ValueError("design_motion requires only a MotionDesignSpec")
        if self.intent == "conversation" and (self.plan is not None or self.design is not None):
            raise ValueError("conversation cannot carry control content")
        return self
