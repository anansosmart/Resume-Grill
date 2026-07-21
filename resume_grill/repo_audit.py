from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


TEXT_EXTS = {
    ".py", ".ipynb", ".md", ".txt", ".toml", ".yaml", ".yml", ".json",
    ".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".cpp", ".h", ".hpp",
    ".sh", ".bat", ".ps1", ".csv"
}
IGNORE_DIRS = {".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__", ".next"}


@dataclass
class RepoSnapshot:
    source: str
    root: Path
    files: list[Path]
    corpus: str
    commit_authors: list[str]
    commit_count: int
    has_tests: bool
    has_benchmarks: bool
    has_results: bool

    def cleanup(self) -> None:
        for candidate in (self.root, *self.root.parents):
            if candidate.name.startswith(("resume_grill_repo_", "resume_grill_zip_")):
                shutil.rmtree(candidate, ignore_errors=True)
                return


def _safe_files(root: Path, limit: int = 1200) -> Iterable[Path]:
    count = 0
    for path in root.rglob("*"):
        if count >= limit:
            break
        if path.is_symlink() or not path.is_file() or any(part in IGNORE_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_EXTS or path.stat().st_size > 1_500_000:
            continue
        count += 1
        yield path


def _build_snapshot(root: Path, source: str) -> RepoSnapshot:
    files = list(_safe_files(root))
    chunks: list[str] = []
    for path in files:
        try:
            rel = path.relative_to(root)
            text = path.read_text("utf-8", errors="ignore")
            chunks.append(f"\n### FILE: {rel}\n{text[:80_000]}")
        except OSError:
            continue
    corpus = "\n".join(chunks)[:8_000_000]

    authors: list[str] = []
    commit_count = 0
    if (root / ".git").exists():
        try:
            raw = subprocess.check_output(
                ["git", "-C", str(root), "log", "--format=%an <%ae>", "-n", "500"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=15,
            )
            authors = sorted(set(line.strip() for line in raw.splitlines() if line.strip()))
            commit_count = len(raw.splitlines())
        except Exception:
            pass

    names = [str(p.relative_to(root)).lower() for p in files]
    has_tests = any("test" in n for n in names)
    has_benchmarks = any(any(k in n for k in ("benchmark", "bench", "profile", "latency", "throughput")) for n in names)
    has_results = any(any(k in n for k in ("result", "report", "metrics", "log", "evaluation", "eval")) for n in names)
    return RepoSnapshot(source, root, files, corpus, authors, commit_count, has_tests, has_benchmarks, has_results)


def clone_public_repo(url: str) -> RepoSnapshot:
    if not re.match(r"^https://github\.com/[\w.-]+/[\w.-]+/?$", url.strip()):
        raise ValueError("目前只接受形如 https://github.com/用户名/仓库名 的公开仓库链接。")
    temp_root = Path(tempfile.mkdtemp(prefix="resume_grill_repo_"))
    repo_dir = temp_root / "repo"
    try:
        subprocess.run(
            ["git", "-c", "core.symlinks=false", "-c", "filter.lfs.smudge=", "-c", "filter.lfs.required=false", "clone", "--depth", "100", url.strip(), str(repo_dir)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=90,
        )
    except Exception as exc:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise RuntimeError(f"仓库下载失败：{exc}") from exc
    return _build_snapshot(repo_dir, url.strip())


def open_repo_zip(filename: str, data: bytes) -> RepoSnapshot:
    temp_root = Path(tempfile.mkdtemp(prefix="resume_grill_zip_"))
    zip_path = temp_root / "repo.zip"
    zip_path.write_bytes(data)
    extract_dir = temp_root / "repo"
    extract_dir.mkdir()
    try:
        with zipfile.ZipFile(zip_path) as zf:
            infos = zf.infolist()
            if len(infos) > 5000 or sum(i.file_size for i in infos) > 150_000_000:
                raise ValueError("ZIP 文件过大或文件数量过多。")
            for info in infos:
                target = (extract_dir / info.filename).resolve()
                if extract_dir.resolve() not in target.parents and target != extract_dir.resolve():
                    raise ValueError("ZIP 中存在不安全路径。")
            zf.extractall(extract_dir)
    except Exception as exc:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise RuntimeError(f"仓库 ZIP 解压失败：{exc}") from exc

    children = [p for p in extract_dir.iterdir() if p.is_dir()]
    root = children[0] if len(children) == 1 else extract_dir
    return _build_snapshot(root, filename)


def evidence_for_claim(claim: str, snapshot: RepoSnapshot | None, candidate_identity: str = "") -> dict:
    if snapshot is None:
        return {
            "score": 0, "matched_keywords": [], "matched_numbers": [], "files": [],
            "snippets": [], "notes": ["未提供 GitHub 仓库或代码 ZIP。"]
        }

    corpus_low = snapshot.corpus.lower()
    keywords = [
        w for w in re.findall(r"[A-Za-z][A-Za-z0-9+_.-]{2,}|[\u4e00-\u9fff]{2,8}", claim)
        if w.lower() not in {"使用", "实现", "进行", "负责", "项目", "模型", "数据", "基于", "通过", "以及"}
    ]
    keywords = list(dict.fromkeys(keywords))[:30]
    matched_keywords = [w for w in keywords if w.lower() in corpus_low]
    numbers = re.findall(r"\d+(?:\.\d+)?%?|\d+[kKmMbB]?", claim)
    matched_numbers = [n for n in numbers if n.lower() in corpus_low]

    matched_files: list[str] = []
    snippets: list[str] = []
    important = matched_keywords[:8] + matched_numbers[:5]
    for path in snapshot.files:
        if len(matched_files) >= 8:
            break
        try:
            text = path.read_text("utf-8", errors="ignore")
        except OSError:
            continue
        low = text.lower()
        if important and any(token.lower() in low for token in important):
            matched_files.append(str(path.relative_to(snapshot.root)))
            for token in important:
                idx = low.find(token.lower())
                if idx >= 0:
                    snippet = " ".join(text[max(0, idx - 80): idx + 180].split())
                    snippets.append(f"{path.name}: {snippet[:240]}")
                    break

    score = 0
    if keywords:
        score += min(35, round(35 * len(matched_keywords) / max(1, len(keywords))))
    if numbers:
        score += min(30, round(30 * len(matched_numbers) / len(numbers)))
    else:
        score += 10
    if matched_files:
        score += 10
    if snapshot.has_tests:
        score += 8
    if snapshot.has_benchmarks:
        score += 10
    if snapshot.has_results:
        score += 7

    notes = []
    if numbers and not matched_numbers:
        notes.append("简历中的关键数字未在仓库文本、日志或报告中找到。")
    if not snapshot.has_benchmarks and re.search(r"提升|降低|吞吐|延迟|准确率|IoU|F1|AUC", claim, re.I):
        notes.append("仓库中未发现明显的 benchmark / profile 脚本。")
    if not snapshot.has_results and numbers:
        notes.append("仓库中未发现明显的结果、日志或评估文件。")
    if candidate_identity and snapshot.commit_authors:
        identity_low = candidate_identity.lower()
        if not any(identity_low in author.lower() for author in snapshot.commit_authors):
            notes.append("Git 提交作者中未匹配到填写的姓名或邮箱；可能是账号名称不同，需人工核对。")
            score -= 8
    return {
        "score": max(0, min(100, score)),
        "matched_keywords": matched_keywords[:12],
        "matched_numbers": matched_numbers[:8],
        "files": matched_files,
        "snippets": snippets[:5],
        "notes": notes,
    }
