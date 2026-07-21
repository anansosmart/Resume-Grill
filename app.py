from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from resume_grill.audit import audit_resume
from resume_grill.llm import (
    BACKUP_MODELS,
    DEFAULT_MODEL,
    evaluate_answer,
    list_ollama_models,
    ollama_available,
)
from resume_grill.parser import ResumeParseError, parse_resume_bytes
from resume_grill.pdf_report import generate_pdf
from resume_grill.repo_audit import clone_public_repo, open_repo_zip

APP_VERSION = "2.0.0"
BASE_DIR = Path(__file__).resolve().parent
SAMPLE_PATH = BASE_DIR / "examples" / "sample_resume.txt"

st.set_page_config(page_title="AI简历拷打机 V2", page_icon="🔥", layout="wide")

st.markdown(
    """
<style>
.block-container {max-width: 1180px; padding-top: 1.1rem; padding-bottom: 3rem;}
.hero {padding: 30px 32px; border-radius: 24px; background: linear-gradient(135deg,#111827,#7f1d1d); color:white; margin-bottom:16px; box-shadow:0 18px 45px rgba(17,24,39,.16);}
.hero h1 {font-size:42px; margin:0 0 8px 0;}
.hero p {font-size:18px; opacity:.94; margin:0;}
.privacy {border:2px solid #10b981; background:#ecfdf5; padding:16px 18px; border-radius:16px; margin:12px 0 18px; color:#064e3b; font-weight:650;}
.demo-card {border:1px solid #fecaca; background:linear-gradient(135deg,#fff7ed,#fff1f2); padding:20px 22px; border-radius:18px; margin:12px 0 22px;}
.demo-card h3 {margin:0 0 7px 0; color:#7f1d1d;}
.warning {border-left:5px solid #f59e0b; background:#fffbeb; padding:12px 16px; border-radius:8px;}
.small {color:#6b7280;font-size:13px;}
.badge {display:inline-block;padding:5px 10px;border-radius:999px;background:#111827;color:#fff;font-size:12px;margin-right:6px;}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown(
    f"""
<div class="hero">
  <span class="badge">V{APP_VERSION}</span>
  <span class="badge">本地隐私</span>
  <span class="badge">PDF报告</span>
  <h1>🔥 AI 简历拷打机</h1>
  <p>逐条检查量化成果、GitHub证据与疑似夸大风险，再模拟技术面试官继续追问。</p>
</div>
<div class="privacy">
🔒 严肃隐私声明：作者看不到你上传的简历。本项目没有作者服务器、没有账号系统、没有后台数据库、没有遥测。
简历只在你自己的电脑上解析。使用 Ollama 本地模型时，简历内容不会离开你的电脑。
</div>
""",
    unsafe_allow_html=True,
)


def run_audit(
    *,
    resume_text: str,
    resume_name: str,
    model_mode: str,
    model: str,
    repo_url: str = "",
    repo_zip_name: str | None = None,
    repo_zip_data: bytes | None = None,
    identity: str = "",
    jd: str = "",
) -> None:
    """Run one audit and persist the result in Streamlit session state."""
    repo = None
    try:
        with st.status("正在进行本地审计……", expanded=True) as status:
            if repo_zip_name and repo_zip_data:
                st.write("正在静态分析代码 ZIP……")
                repo = open_repo_zip(repo_zip_name, repo_zip_data)
            elif repo_url.strip():
                st.write("正在下载公开 GitHub 仓库，只分析本地副本……")
                repo = clone_public_repo(repo_url.strip())

            st.write("正在提取量化声明、责任边界和证据缺口……")
            use_ollama = model_mode.startswith("Ollama") and ollama_available()
            model_used = model if use_ollama else "规则引擎"
            report = audit_resume(
                resume_text,
                resume_name,
                repo=repo,
                candidate_identity=identity,
                model_used=model_used,
            )
            st.session_state["report"] = report
            st.session_state["resume_text"] = resume_text
            st.session_state["jd"] = jd
            st.session_state["is_demo"] = resume_name.startswith("虚构演示")
            status.update(label="审计完成", state="complete")
    finally:
        if repo is not None:
            repo.cleanup()


with st.sidebar:
    st.header("运行模式")
    model_mode = st.radio(
        "分析引擎",
        ["规则引擎（最快、完全离线）", "Ollama 本地模型增强"],
        index=0,
    )
    installed = list_ollama_models() if model_mode.startswith("Ollama") else []
    choices = installed or [DEFAULT_MODEL, *BACKUP_MODELS]
    model = st.selectbox("本地模型", choices, disabled=not model_mode.startswith("Ollama"))
    if model_mode.startswith("Ollama"):
        if ollama_available():
            st.success("Ollama 已连接")
        else:
            st.error("未检测到 Ollama，将自动使用规则引擎。")
    st.divider()
    st.caption("推荐：qwen2.5:7b-instruct。显存不足可用 llama3.2:3b。")
    st.caption("本项目不会执行仓库代码，只做静态分析。")

st.markdown(
    """
<div class="demo-card">
<h3>⚡ 第一次使用？先跑一个虚构 Demo</h3>
无需上传任何文件。系统会审计一份故意写得很“夸张”的虚构简历，展示风险热力图、追问和 PDF 报告。
</div>
""",
    unsafe_allow_html=True,
)

demo_col, clear_col = st.columns([3, 1])
with demo_col:
    demo_clicked = st.button("⚡ 立即体验 Demo（无需上传）", type="primary", use_container_width=True)
with clear_col:
    if st.button("清空当前结果", use_container_width=True):
        for key in ("report", "resume_text", "jd", "is_demo"):
            st.session_state.pop(key, None)
        st.rerun()

if demo_clicked:
    try:
        demo_text = SAMPLE_PATH.read_text("utf-8")
        run_audit(
            resume_text=demo_text,
            resume_name="虚构演示简历.txt",
            model_mode=model_mode,
            model=model,
        )
    except Exception as exc:  # Streamlit should display instead of closing.
        st.error(f"Demo 启动失败：{exc}")

st.divider()
st.subheader("审计我自己的简历")
resume_file = st.file_uploader("1. 上传简历", type=["pdf", "docx", "txt", "md"])
col1, col2 = st.columns(2)
with col1:
    repo_url = st.text_input(
        "2. GitHub公开仓库（可选）",
        placeholder="https://github.com/username/repository",
    )
with col2:
    repo_zip = st.file_uploader("或上传代码仓库 ZIP（可选）", type=["zip"])
identity = st.text_input("3. 你的 Git 提交姓名或邮箱（可选，用于核对个人贡献）")
jd = st.text_area(
    "4. 目标岗位 JD（可选）",
    height=100,
    placeholder="粘贴岗位要求，可帮助你准备更有针对性的回答。",
)

if st.button("开始审计我的简历", type="primary", use_container_width=True):
    try:
        if not resume_file:
            st.error("请先上传简历；只想体验功能可以点击上方 Demo。")
        else:
            resume_text = parse_resume_bytes(resume_file.name, resume_file.getvalue())
            run_audit(
                resume_text=resume_text,
                resume_name=resume_file.name,
                model_mode=model_mode,
                model=model,
                repo_url=repo_url,
                repo_zip_name=repo_zip.name if repo_zip else None,
                repo_zip_data=repo_zip.getvalue() if repo_zip else None,
                identity=identity,
                jd=jd,
            )
    except (ResumeParseError, ValueError, RuntimeError) as exc:
        st.error(str(exc))
    except Exception as exc:
        st.error(f"运行失败：{exc}")
        st.info("请查看项目目录中的“启动日志.txt”，或使用 START_WINDOWS.bat 再次启动。")

report = st.session_state.get("report")
if report:
    st.divider()
    if st.session_state.get("is_demo"):
        st.info("当前显示的是虚构 Demo。所有姓名、项目和数据均为虚构，不对应任何真实求职者。")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("抗追问分", report.overall_score)
    c2.metric("证据完整度", report.evidence_score)
    c3.metric("量化可信度", report.metric_score)
    c4.metric("疑似夸大风险", report.exaggeration_risk)
    st.markdown(
        f"<div class='warning'><b>重要：</b>{report.disclaimer}</div>",
        unsafe_allow_html=True,
    )
    st.write(report.summary)
    for flag in report.global_flags:
        st.warning(flag)

    st.subheader("逐条风险地图")
    for i, claim in enumerate(report.claims, 1):
        icon = {"严重": "🔴", "高": "🟠", "中": "🟡", "低": "🟢"}.get(claim.risk_level, "⚪")
        title = (
            f"{icon} {i}. {claim.risk_level}风险 · {claim.category} · "
            f"风险 {claim.risk_score} / 证据 {claim.evidence_score}"
        )
        with st.expander(title, expanded=i <= 2):
            st.markdown(f"**原文：** {claim.claim}")
            st.markdown("**风险信号**")
            for flag in claim.flags:
                st.write(f"- {flag}")
            if claim.missing_evidence:
                st.markdown("**建议补充**")
                for item in claim.missing_evidence:
                    st.write(f"- {item}")
            if claim.evidence.files:
                st.markdown("**匹配到的仓库文件**")
                st.code("\n".join(claim.evidence.files), language="text")
            st.markdown("**面试官可能追问**")
            for q in claim.questions:
                st.write(f"- {q}")

    if report.claims:
        st.subheader("现场回答一条追问")
        labels = [f"{i + 1}. {c.claim[:65]}" for i, c in enumerate(report.claims)]
        selected_idx = st.selectbox(
            "选择声明",
            range(len(labels)),
            format_func=lambda x: labels[x],
        )
        selected = report.claims[selected_idx]
        question = st.selectbox("选择问题", selected.questions)
        answer = st.text_area("输入你的回答", height=150)
        if st.button("评估回答并继续追问"):
            if not answer.strip():
                st.error("请先输入回答。")
            elif model_mode.startswith("Ollama") and ollama_available():
                try:
                    result = evaluate_answer(selected.claim, question, answer, model)
                    st.metric("回答可信度", result.get("score", 0))
                    st.write(f"**判断：** {result.get('verdict', '')}")
                    st.write("**优点：**", "；".join(result.get("strengths", [])) or "无")
                    st.write("**缺口：**", "；".join(result.get("gaps", [])) or "无")
                    st.error(f"继续追问：{result.get('follow_up', '')}")
                except Exception as exc:
                    st.error(f"本地模型评估失败：{exc}")
            else:
                needed = ["baseline", "数据", "代码", "日志", "本人", "环境", "复现"]
                hits = sum(k.lower() in answer.lower() for k in needed)
                score = min(88, 30 + hits * 9 + min(20, len(answer) // 40))
                st.metric("回答准备度（规则估算）", score)
                st.error("继续追问：请指出具体代码文件、实验命令和原始日志位置。")

    pdf = generate_pdf(report)
    pdf_name = "AI简历拷打机_Demo报告.pdf" if st.session_state.get("is_demo") else "AI简历拷打报告.pdf"
    st.download_button(
        "下载完整 PDF 报告",
        pdf,
        file_name=pdf_name,
        mime="application/pdf",
        type="primary",
        use_container_width=True,
    )
    st.download_button(
        "下载 JSON 数据",
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        file_name="audit.json",
        mime="application/json",
        use_container_width=True,
    )

st.divider()
st.subheader("第一次用 GitHub？只需要三步")
st.markdown(
    "1. 下载本项目 ZIP 并**完整解压**。\n"
    "2. Windows 双击 `启动中文版.bat`；如果中文文件名显示异常，双击 `START_WINDOWS.bat`。\n"
    "3. 浏览器打开后，先点 Demo 或上传自己的简历。"
)
st.caption("不会上传到作者服务器。不要把身份证、住址、银行卡等无关敏感信息写进简历。")
