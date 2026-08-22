"""Frozen, reviewable official evidence for the CNN candidate demonstration."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

EvidenceType = Literal["definition", "code", "derived_exercise"]
SourceType = Literal["official_source", "system_derived"]
ReviewStatus = Literal["candidate", "reviewed", "approved"]
LicenseStatus = Literal["unverified", "confirmed"]


class FrozenEvidence(BaseModel):
    """Page and span hashes preserve what was reviewed, even if a page changes later."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_id: str = Field(min_length=1)
    evidence_type: EvidenceType
    source_type: SourceType
    source_url: HttpUrl | None = None
    resolved_url: HttpUrl | None = None
    source_title: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    retrieved_at: datetime
    page_text_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    span_text: str = Field(min_length=1)
    span_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    span_locator: str = Field(min_length=1)
    license_status: LicenseStatus
    review_status: ReviewStatus
    reviewer: str | None = None
    reviewed_at: datetime | None = None
    parent_evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_provenance(self) -> FrozenEvidence:
        if sha256(self.span_text.encode("utf-8")).hexdigest() != self.span_hash:
            raise ValueError("span hash does not match span text")
        if self.evidence_type == "derived_exercise":
            if self.source_type != "system_derived" or not self.parent_evidence_ids:
                raise ValueError("derived exercises require system source and parent evidence")
        elif self.source_type != "official_source" or self.parent_evidence_ids:
            raise ValueError("official evidence cannot carry derived source metadata")
        if self.review_status in {"reviewed", "approved"} and (
            not self.reviewer or self.reviewed_at is None
        ):
            raise ValueError("reviewed evidence requires reviewer and timestamp")
        return self


class EvidenceBundleManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    bundle_id: str = Field(pattern=r"^cnn_demo_evidence_[0-9a-f]{64}$")
    concept_id: str = "dl.cnn.convolution"
    version: str = "cnn-demo-evidence.v1"
    records: tuple[FrozenEvidence, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_bundle(self) -> EvidenceBundleManifest:
        ids = [record.evidence_id for record in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("evidence IDs must be unique")
        for record in self.records:
            if record.evidence_type == "derived_exercise" and not set(
                record.parent_evidence_ids
            ).issubset(ids):
                raise ValueError("derived exercise parent evidence is missing from the bundle")
        expected = build_bundle_id(self.model_dump(mode="json", exclude={"bundle_id"}))
        if self.bundle_id != expected:
            raise ValueError("evidence bundle identity does not match content")
        return self

    @classmethod
    def create(cls, *, records: tuple[FrozenEvidence, ...]) -> EvidenceBundleManifest:
        payload = {
            "concept_id": "dl.cnn.convolution",
            "version": "cnn-demo-evidence.v1",
            "records": [item.model_dump(mode="json") for item in records],
        }
        return cls(**payload, bundle_id=build_bundle_id(payload))


def build_bundle_id(payload: object) -> str:
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return f"cnn_demo_evidence_{sha256(canonical.encode('utf-8')).hexdigest()}"


def freeze_web_evidence(
    *,
    evidence_id: str,
    evidence_type: Literal["definition", "code"],
    source_url: str,
    source_title: str,
    source_version: str,
    span_text: str,
    span_locator: str,
    review_status: ReviewStatus = "candidate",
    reviewer: str | None = None,
    reviewed_at: datetime | None = None,
    license_status: LicenseStatus = "unverified",
) -> FrozenEvidence:
    """Fetch page text once to freeze a page hash; caller selects the reviewed span."""
    response = httpx.get(source_url, follow_redirects=True, timeout=20)
    response.raise_for_status()
    page_text = _normalized_page_text(response.text)
    if _normalized_page_text(span_text) not in page_text:
        redirect_target = _documentation_redirect_target(response.text, response.url)
        if redirect_target is not None:
            response = httpx.get(redirect_target, follow_redirects=True, timeout=20)
            response.raise_for_status()
            page_text = _normalized_page_text(response.text)
    if _normalized_page_text(span_text) not in page_text:
        raise ValueError("selected evidence span was not found in fetched page text")
    return FrozenEvidence(
        evidence_id=evidence_id,
        evidence_type=evidence_type,
        source_type="official_source",
        source_url=source_url,
        resolved_url=str(response.url),
        source_title=source_title,
        source_version=source_version,
        retrieved_at=datetime.now(UTC),
        page_text_hash=sha256(page_text.encode("utf-8")).hexdigest(),
        span_text=span_text,
        span_hash=sha256(span_text.encode("utf-8")).hexdigest(),
        span_locator=span_locator,
        license_status=license_status,
        review_status=review_status,
        reviewer=reviewer,
        reviewed_at=reviewed_at,
    )


def derive_exercise(
    *,
    evidence_id: str,
    prompt: str,
    parent_evidence_ids: tuple[str, ...],
    reviewer: str | None = None,
    reviewed_at: datetime | None = None,
) -> FrozenEvidence:
    return FrozenEvidence(
        evidence_id=evidence_id,
        evidence_type="derived_exercise",
        source_type="system_derived",
        source_title="SkillForge derived CNN exercise",
        source_version="cnn-demo-evidence.v1",
        retrieved_at=datetime.now(UTC),
        page_text_hash=sha256(prompt.encode("utf-8")).hexdigest(),
        span_text=prompt,
        span_hash=sha256(prompt.encode("utf-8")).hexdigest(),
        span_locator="derived-exercise",
        license_status="unverified",
        review_status="reviewed" if reviewer else "candidate",
        reviewer=reviewer,
        reviewed_at=reviewed_at,
        parent_evidence_ids=parent_evidence_ids,
    )


CNN_DEMO_SOURCES = (
    {
        "evidence_id": "E-CNN-DEF-001",
        "evidence_type": "definition",
        "source_url": "https://docs.pytorch.org/docs/stable/generated/torch.nn.Conv2d.html",
        "source_title": "torch.nn.Conv2d",
        "span_text": (
            "Applies a 2D convolution over an input signal composed of several input planes."
        ),
        "span_locator": "torch.nn.Conv2d / description",
    },
    {
        "evidence_id": "E-CNN-CODE-001",
        "evidence_type": "code",
        "source_url": "https://docs.pytorch.org/docs/stable/generated/torch.nn.Conv2d.html",
        "source_title": "torch.nn.Conv2d",
        "span_text": "nn.Conv2d(16, 33, 3, stride=2)",
        "span_locator": "torch.nn.Conv2d / examples",
    },
    {
        "evidence_id": "E-TENSOR-DEF-001",
        "evidence_type": "definition",
        "source_url": "https://docs.pytorch.org/tutorials/beginner/basics/tensorqs_tutorial.html",
        "source_title": "Tensors",
        "span_text": (
            "Tensors are a specialized data structure that are very similar to arrays and matrices."
        ),
        "span_locator": "Tensors / introduction",
    },
)


def freeze_cnn_demo_bundle(
    *, reviewer: str | None = None, license_confirmed: bool = False
) -> EvidenceBundleManifest:
    """Fetch and freeze the official CNN demo spans; review status needs a named reviewer."""
    reviewed_at = datetime.now(UTC) if reviewer else None
    status: ReviewStatus = "reviewed" if reviewer else "candidate"
    license_status: LicenseStatus = "confirmed" if license_confirmed else "unverified"
    records = tuple(
        freeze_web_evidence(
            **source,
            source_version="stable",
            review_status=status,
            reviewer=reviewer,
            reviewed_at=reviewed_at,
            license_status=license_status,
        )
        for source in CNN_DEMO_SOURCES
    )
    derived = derive_exercise(
        evidence_id="E-CNN-EX-001",
        prompt="Use the reviewed Conv2d definition and example to predict an output tensor shape.",
        parent_evidence_ids=("E-CNN-DEF-001", "E-CNN-CODE-001"),
        reviewer=reviewer,
        reviewed_at=reviewed_at,
    )
    return EvidenceBundleManifest.create(records=(*records, derived))


def as_allowed_evidence(bundle: EvidenceBundleManifest) -> tuple[object, ...]:
    """Translate frozen records into the generation-policy evidence contract."""
    from .controlled_generation import AllowedEvidence, EvidenceApprovalStatus

    return tuple(
        AllowedEvidence(
            evidence_id=record.evidence_id,
            source_id=record.source_title,
            span_id=record.span_locator,
            text=record.span_text,
            approval_status=EvidenceApprovalStatus(record.review_status),
        )
        for record in bundle.records
    )


def write_review_checklist(bundle: EvidenceBundleManifest, path: Path) -> Path:
    lines = [
        "# CNN Demo Evidence Review Checklist",
        "",
        "Review each source before marking it `reviewed`.",
        "",
    ]
    for record in bundle.records:
        lines.extend(
            [
                f"## {record.evidence_id} ({record.evidence_type})",
                f"- Status: `{record.review_status}`; License: `{record.license_status}`",
                f"- Source: {record.resolved_url or 'system derived'}",
                f"- Locator: {record.span_locator}",
                f"- Page hash: `{record.page_text_hash}`",
                f"- Span hash: `{record.span_hash}`",
                f"- Reviewer: {record.reviewer or '[pending]'}",
                "- Confirm scope, wording, license, and parent evidence where applicable.",
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _normalized_page_text(text: str) -> str:
    """Stable plain-text representation used for page hashing and span lookup."""
    without_tags = re.sub(r"<[^>]+>", " ", text)
    return " ".join(without_tags.replace("&nbsp;", " ").split())


def _documentation_redirect_target(page: str, page_url: object) -> str | None:
    """Follow PyTorch stable-doc JavaScript redirects while retaining the resolved version."""
    match = re.search(r'location\.replace\("([^"]+)"', page)
    if match is None:
        return None
    relative = match.group(1).split('" + location.hash', maxsplit=1)[0]
    return str(httpx.URL(str(page_url)).join(relative))
