import json
from hashlib import sha256

from .models import PlannerPolicy


def build_policy_digest(policy: PlannerPolicy) -> str:
    canonical = json.dumps(
        policy.model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return f"policy_{sha256(canonical.encode('utf-8')).hexdigest()}"


def build_path_id(
    profile_id: str,
    graph_version: str,
    policy_version: str,
    concept_ids: list[str],
    policy_digest: str | None = None,
) -> str:
    payload = {
        "concept_ids": concept_ids,
        "graph_version": graph_version,
        "policy_version": policy_version,
        "profile_id": profile_id,
    }
    if policy_digest is not None:
        payload["policy_digest"] = policy_digest
    canonical = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return f"path_{sha256(canonical.encode('utf-8')).hexdigest()}"
