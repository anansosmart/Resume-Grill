from __future__ import annotations

import argparse
from pathlib import Path

from .audit import audit_resume
from .parser import parse_resume_bytes
from .pdf_report import generate_pdf


def main() -> None:
    parser = argparse.ArgumentParser(description="AI简历拷打机：在本地审计简历并输出PDF。")
    parser.add_argument("resume", help="PDF、DOCX、TXT 或 Markdown 简历路径")
    parser.add_argument("-o", "--output", default="report.pdf", help="输出PDF路径")
    args = parser.parse_args()
    path = Path(args.resume)
    text = parse_resume_bytes(path.name, path.read_bytes())
    report = audit_resume(text, path.name)
    Path(args.output).write_bytes(generate_pdf(report))
    print(f"已生成：{Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
