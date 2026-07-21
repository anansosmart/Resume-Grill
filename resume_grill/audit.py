from __future__ import annotations

import re
from datetime import datetime
from statistics import mean

from .models import AuditReport, ClaimAudit, Evidence
from .repo_audit import RepoSnapshot, evidence_for_claim

ACTION_WORDS = re.compile(r"负责|主导|独立|从零|构建|设计|实现|优化|提升|降低|完成|开发|训练|部署|发表|获得|排名|精通|熟练")
METRIC_WORDS = re.compile(r"准确率|召回率|F1|AUC|IoU|吞吐|延迟|显存|速度|性能|成本|错误率|违规率|Top|排名", re.I)
BASELINE_WORDS = re.compile(r"基线|baseline|相比|before|after|对照|由\s*\d+(?:\.\d+)?%?\s*(?:提升|增加|降低|下降)?\s*(?:至|到)|从\s*\d+(?:\.\d+)?%?\s*(?:至|到)", re.I)
CONTEXT_WORDS = re.compile(r"数据集|样本|训练集|测试集|验证集|并发|batch|输入长度|输出长度|硬件|GPU|A100|实验", re.I)
PROOF_WORDS = re.compile(r"DOI|论文链接|代码链接|GitHub|证书|获奖链接|报告|日志|benchmark", re.I)
STACK_WORDS = re.compile(r"PyTorch|TensorFlow|Qwen|Llama|vLLM|CUDA|ONNX|RAG|Agent|QLoRA|LoRA|FedAvg|Docker|Kubernetes|FastAPI|React|Transformers", re.I)


def _candidate_claims(text: str) -> list[str]:
    raw: list[str] = []
    for line in text.splitlines():
        line = re.sub(r"^[•·\-*▪◦\s]+", "", line).strip()
        if re.search(r"本科|硕士|博士", line) and re.search(r"20\d{2}[.\-/]\d{1,2}.*20\d{2}[.\-/]\d{1,2}", line) and not ACTION_WORDS.search(line):
            continue
        if 18 <= len(line) <= 360 and (ACTION_WORDS.search(line) or re.search(r"\d", line)):
            raw.append(line)
    dedup: list[str] = []
    seen = set()
    for item in raw:
        norm = re.sub(r"\s+", "", item)
        if norm not in seen:
            dedup.append(item)
            seen.add(norm)
    return dedup[:30]


def _category(claim: str) -> str:
    if re.search(r"论文|IEEE|SCI|会议|专利|最佳论文", claim, re.I):
        return "论文/荣誉"
    if re.search(r"排名|Top|奖牌|竞赛|Kaggle", claim, re.I):
        return "竞赛"
    if METRIC_WORDS.search(claim) or "%" in claim:
        return "量化成果"
    if re.search(r"精通|熟练掌握|技能", claim):
        return "技能声明"
    return "项目职责"


def _risk_label(score: int) -> str:
    if score >= 76:
        return "严重"
    if score >= 56:
        return "高"
    if score >= 31:
        return "中"
    return "低"


def _questions(claim: str, flags: list[str], missing: list[str]) -> list[str]:
    questions = [
        f"请用 60 秒说明这条经历中你本人真正完成的部分：{claim}",
        "请指出对应的代码文件、核心函数或实验脚本，并说明你修改了什么。",
    ]
    if re.search(r"\d", claim):
        questions.extend([
            "这些数字的 baseline、数据划分、硬件环境和重复实验次数分别是什么？",
            "原始日志在哪里？如果重新运行，别人能否复现同样的结果？",
        ])
    if "责任边界不清" in flags or re.search(r"独立|主导|从零", claim):
        questions.append("团队中还有谁参与？哪些工作不是你做的？")
    if "论文或荣誉缺少可核验入口" in flags:
        questions.append("请提供论文检索页、DOI、获奖名单或官方排名页面。")
    if "技术栈过密" in flags:
        questions.append("这些技术中哪些只是调用过，哪些你能解释底层原理并现场调试？")
    for item in missing[:2]:
        questions.append(f"你准备如何补齐这项证据：{item}？")
    return list(dict.fromkeys(questions))[:7]


def audit_resume(
    resume_text: str,
    resume_name: str,
    repo: RepoSnapshot | None = None,
    candidate_identity: str = "",
    model_used: str = "规则引擎",
) -> AuditReport:
    claims = _candidate_claims(resume_text)
    audits: list[ClaimAudit] = []
    global_flags: list[str] = []

    for claim in claims:
        risk = 8
        flags: list[str] = []
        missing: list[str] = []
        numbers = re.findall(r"\d+(?:\.\d+)?%?", claim)
        category = _category(claim)

        if numbers and category == "量化成果":
            risk += 13
            if not BASELINE_WORDS.search(claim):
                risk += 15
                flags.append("量化结果缺少明确 baseline")
                missing.append("基线配置和修改前结果")
            if not CONTEXT_WORDS.search(claim):
                risk += 13
                flags.append("缺少实验上下文")
                missing.append("数据规模、划分、硬件和测试设置")
            if len(numbers) >= 3:
                risk += 6
                flags.append("精确数字较多，面试官会要求原始记录")
                missing.append("原始日志或结果表")
        elif numbers:
            risk += 5

        if re.search(r"独立|主导|从零", claim):
            risk += 13
            flags.append("责任边界不清")
            missing.append("个人贡献与团队贡献的边界")

        stack_count = len(set(m.group(0).lower() for m in STACK_WORDS.finditer(claim)))
        if stack_count >= 5:
            risk += 12
            flags.append("技术栈过密")
            missing.append("每项技术的具体使用位置")

        if re.search(r"论文|IEEE|SCI|最佳论文|奖牌|Top\s*\d|排名", claim, re.I) and not PROOF_WORDS.search(claim):
            risk += 18
            flags.append("论文或荣誉缺少可核验入口")
            missing.append("官方检索页、DOI、证书或排名链接")

        if re.search(r"精通|专家|全面掌握|熟练掌握", claim):
            risk += 16
            flags.append("能力表述过满")
            missing.append("可证明熟练度的项目或公开作品")
        if re.search(r"行业领先|国际领先|世界领先|SOTA|最先进|首个|唯一", claim, re.I):
            risk += 15
            flags.append("绝对化或领先性表述需要强证据")
            missing.append("同类方法对比、公开榜单或第三方验证")

        evidence_dict = evidence_for_claim(claim, repo, candidate_identity)
        evidence = Evidence(**evidence_dict)
        if repo is None:
            risk += 8
        else:
            if evidence.score < 25:
                risk += 20
                flags.append("代码证据严重不足")
                missing.append("与声明直接对应的代码、实验脚本或结果")
            elif evidence.score < 50:
                risk += 10
                flags.append("代码证据不完整")
                missing.append("更清晰的README、结果日志或复现命令")
            if evidence.notes:
                flags.extend(evidence.notes)

        risk = max(0, min(100, risk))
        audits.append(ClaimAudit(
            claim=claim,
            category=category,
            risk_score=risk,
            evidence_score=evidence.score,
            risk_level=_risk_label(risk),
            flags=list(dict.fromkeys(flags)) or ["暂未发现明显高风险信号"],
            missing_evidence=list(dict.fromkeys(missing)),
            questions=_questions(claim, flags, missing),
            evidence=evidence,
        ))

    if not audits:
        global_flags.append("未识别到足够具体的项目声明；简历可能过于空泛。")

    risk_values = [a.risk_score for a in audits] or [65]
    evidence_values = [a.evidence_score for a in audits] or [0]
    metric_claims = [a for a in audits if a.category == "量化成果"]
    metric_score = round(100 - mean([a.risk_score for a in metric_claims])) if metric_claims else 45
    evidence_score = round(mean(evidence_values))
    top_risks = sorted(risk_values, reverse=True)[: max(1, min(3, len(risk_values)))]
    exaggeration_risk = round(0.55 * max(top_risks) + 0.45 * mean(top_risks))
    overall = max(0, min(100, round(0.42 * (100 - exaggeration_risk) + 0.38 * evidence_score + 0.20 * metric_score)))

    severe_count = sum(a.risk_score >= 76 for a in audits)
    high_count = sum(56 <= a.risk_score < 76 for a in audits)
    if severe_count:
        global_flags.append(f"发现 {severe_count} 条严重追问风险声明，建议在投递前补齐证据或降级措辞。")
    if high_count:
        global_flags.append(f"发现 {high_count} 条高追问风险声明。")
    if repo is None:
        global_flags.append("未提供代码仓库，因此无法核对简历声明与代码、日志、提交记录的一致性。")
    elif repo.commit_count == 0:
        global_flags.append("无法读取有效 Git 提交历史，个人贡献核验能力受限。")

    summary = (
        f"共识别 {len(audits)} 条可追问声明，其中严重风险 {severe_count} 条、高风险 {high_count} 条。"
        "高风险不等于造假，通常表示缺少 baseline、原始日志、责任边界或公开证据。"
    )
    repo_summary = {}
    if repo is not None:
        repo_summary = {
            "source": repo.source,
            "text_files": len(repo.files),
            "commit_count": repo.commit_count,
            "commit_authors": repo.commit_authors[:20],
            "has_tests": repo.has_tests,
            "has_benchmarks": repo.has_benchmarks,
            "has_results": repo.has_results,
        }

    return AuditReport(
        resume_name=resume_name,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        privacy_mode="本地处理；无上传服务器；无遥测",
        overall_score=overall,
        evidence_score=evidence_score,
        metric_score=max(0, metric_score),
        exaggeration_risk=exaggeration_risk,
        summary=summary,
        global_flags=global_flags,
        claims=sorted(audits, key=lambda x: x.risk_score, reverse=True),
        repo_summary=repo_summary,
        model_used=model_used,
    )
