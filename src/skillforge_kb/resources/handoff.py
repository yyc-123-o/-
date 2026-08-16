from typing import ClassVar, Literal

from pydantic import model_validator

from .models import GenerationGate, ResourceBrief


class ResourceHandoffContract(ResourceBrief):
    """Authoritative planning payload consumed by retrieval/resource agents."""

    schema_version: ClassVar[Literal["resource-agent-handoff.v1"]] = (
        "resource-agent-handoff.v1"
    )

    @model_validator(mode="after")
    def validate_handoff_gate(self) -> "ResourceHandoffContract":
        if self.status.value == "blocked" and self.generation_gate.allowed:
            raise ValueError("generation gate does not match blocked handoff")
        return self

    @classmethod
    def from_brief(
        cls,
        brief: ResourceBrief,
        generation_gate: GenerationGate | None = None,
    ) -> "ResourceHandoffContract":
        validated = ResourceBrief.model_validate(brief.model_dump())
        gate = generation_gate or validated.generation_gate
        if gate != validated.generation_gate:
            raise ValueError("generation gate does not match resource brief")
        return cls(**validated.model_dump())
