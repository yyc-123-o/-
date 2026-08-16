from skillforge_kb.agents.resource_tools import ResourceGenerationTool
from skillforge_kb.resources.models import ResourceBrief, build_brief_id


class _FailIfCalledGenerator:
    def __init__(self) -> None:
        self.called = False

    def generate(self, brief, bundle):
        self.called = True
        raise AssertionError("blocked brief must not invoke the generator")


def test_blocked_brief_is_rejected_before_generation(resource_case) -> None:
    brief, bundle = resource_case
    payload = brief.model_dump(mode="json")
    payload["generation_gate"] = {
        "allowed": False,
        "status": "blocked_missing_published_evidence",
        "blocking_codes": ["blocked_missing_published_evidence"],
        "next_action": "publish required evidence before generation",
    }
    payload["brief_id"] = build_brief_id(
        {key: value for key, value in payload.items() if key != "brief_id"}
    )
    blocked = ResourceBrief.model_validate(payload)
    generator = _FailIfCalledGenerator()

    try:
        ResourceGenerationTool().invoke(blocked, bundle, generator)
    except ValueError as exc:
        assert "generation gate" in str(exc)
    else:
        raise AssertionError("blocked brief unexpectedly entered generation")
    assert generator.called is False
