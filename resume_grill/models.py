from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Evidence:
    score: int = 0
    matched_keywords: list[str] = field(default_factory=list)
    matched_numbers: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    snippets: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class ClaimAudit:
    claim: str
    category: str
    risk_score: int
    evidence_score: int
    risk_level: str
    flags: list[str]
    missing_evidence: list[str]
    questions: list[str]
    evidence: Evidence = field(default_factory=Evidence)


@dataclass
class AuditReport:
    resume_name: str
    generated_at: str
    privacy_mode: str
    overall_score: int
    evidence_score: int
    metric_score: int
    exaggeration_risk: int
    summary: str
    global_flags: list[str]
    claims: list[ClaimAudit]
    repo_summary: dict[str, Any] = field(default_factory=dict)
    model_used: str = "规则引擎"
    disclaimer: str = (
        "本报告只识别证据缺口、表述矛盾和高追问风险，不能据此认定任何人造假。"
        "最终判断应结合原始代码、实验日志、证明材料和当事人解释。"
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
