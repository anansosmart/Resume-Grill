from resume_grill.audit import audit_resume
from resume_grill.pdf_report import generate_pdf


def test_audit_and_pdf():
    text = "独立从零使用Qwen、Llama、vLLM、CUDA和Docker开发系统，准确率提升37.8%，速度提升52%。"
    report = audit_resume(text, "demo.txt")
    assert report.claims
    assert report.exaggeration_risk >= 50
    pdf = generate_pdf(report)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 3000
