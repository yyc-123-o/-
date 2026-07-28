import json
from hashlib import sha256


def build_path_id(
    profile_id: str,
    graph_version: str,
    policy_version: str,
    concept_ids: list[str],
) -> str:
    payload = {
        "concept_ids": concept_ids,
        "graph_version": graph_version,
        "policy_version": policy_version,
        "profile_id": profile_id,
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return f"path_{sha256(canonical.encode('utf-8')).hexdigest()}"
