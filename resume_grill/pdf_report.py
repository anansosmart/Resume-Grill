from __future__ import annotations

import io
import math
from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    CondPageBreak,
    Flowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .models import AuditReport, ClaimAudit

# ---------------------------------------------------------------------------
# Typography: use a modern CJK sans-serif when available; remain portable.
# ---------------------------------------------------------------------------
FONT_REGULAR = "STSong-Light"
FONT_BOLD = "STSong-Light"
FONT_SERIF = "STSong-Light"


def _register_fonts() -> None:
    global FONT_REGULAR, FONT_BOLD, FONT_SERIF
    candidates = [
        (
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
            2,
        ),
        (
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/msyhbd.ttc",
            "C:/Windows/Fonts/simsun.ttc",
            0,
        ),
        (
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/Songti.ttc",
            0,
        ),
    ]
    for regular, bold, serif, index in candidates:
        if Path(regular).exists() and Path(bold).exists():
            try:
                pdfmetrics.registerFont(TTFont("RGCN-Regular", regular, subfontIndex=index))
                pdfmetrics.registerFont(TTFont("RGCN-Bold", bold, subfontIndex=index))
                if Path(serif).exists():
                    pdfmetrics.registerFont(TTFont("RGCN-Serif", serif, subfontIndex=index))
                else:
                    pdfmetrics.registerFont(TTFont("RGCN-Serif", regular, subfontIndex=index))
                FONT_REGULAR = "RGCN-Regular"
                FONT_BOLD = "RGCN-Bold"
                FONT_SERIF = "RGCN-Serif"
                return
            except Exception:
                pass
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    except Exception:
        FONT_REGULAR = FONT_BOLD = FONT_SERIF = "Helvetica"


_register_fonts()

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
INK = colors.HexColor("#111827")
INK_2 = colors.HexColor("#334155")
MUTED = colors.HexColor("#64748B")
LINE = colors.HexColor("#E2E8F0")
SURFACE = colors.HexColor("#F8FAFC")
NAVY = colors.HexColor("#0B1220")
NAVY_2 = colors.HexColor("#111C32")
ACCENT = colors.HexColor("#F97316")
ACCENT_SOFT = colors.HexColor("#FFF7ED")
TEAL = colors.HexColor("#0F766E")
TEAL_SOFT = colors.HexColor("#F0FDFA")
RED = colors.HexColor("#B91C1C")
RED_SOFT = colors.HexColor("#FEF2F2")
AMBER = colors.HexColor("#B45309")
AMBER_SOFT = colors.HexColor("#FFFBEB")
GREEN = colors.HexColor("#047857")
GREEN_SOFT = colors.HexColor("#ECFDF5")
WHITE = colors.white

RISK_STYLE = {
    "严重": (RED, RED_SOFT, "CRITICAL"),
    "高": (colors.HexColor("#C2410C"), ACCENT_SOFT, "HIGH"),
    "中": (AMBER, AMBER_SOFT, "MEDIUM"),
    "低": (GREEN, GREEN_SOFT, "LOW"),
}


def _xml(text: str) -> str:
    return escape(str(text)).replace("\n", "<br/>")


def _p(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(_xml(text), style)


def _bullet(text: str, style: ParagraphStyle, color: str = "#475569") -> Paragraph:
    return Paragraph(
        f'<font color="{color}">●</font>&nbsp;&nbsp;{_xml(text)}',
        style,
    )


class RoundedCard(Flowable):
    """A compact non-splitting card for short content blocks."""

    def __init__(
        self,
        children: list[Flowable],
        width: float,
        bg=WHITE,
        border=LINE,
        padding: float = 10,
        radius: float = 10,
        gap: float = 4,
        left_accent=None,
    ):
        super().__init__()
        self.children = children
        self.card_width = width
        self.bg = bg
        self.border = border
        self.padding = padding
        self.radius = radius
        self.gap = gap
        self.left_accent = left_accent
        self._layout: list[tuple[Flowable, float, float]] = []

    def wrap(self, availWidth, availHeight):
        self.width = min(self.card_width, availWidth)
        inner = self.width - 2 * self.padding
        total = 2 * self.padding
        self._layout = []
        for i, child in enumerate(self.children):
            w, h = child.wrap(inner, availHeight)
            self._layout.append((child, w, h))
            total += h
            if i < len(self.children) - 1:
                total += self.gap
        self.height = total
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.saveState()
        c.setFillColor(self.bg)
        c.setStrokeColor(self.border)
        c.setLineWidth(0.7)
        c.roundRect(0, 0, self.width, self.height, self.radius, fill=1, stroke=1)
        if self.left_accent is not None:
            c.setFillColor(self.left_accent)
            c.roundRect(0, 0, 5, self.height, min(5, self.radius), fill=1, stroke=0)
            c.rect(3, 0, 3, self.height, fill=1, stroke=0)
        y = self.height - self.padding
        for child, w, h in self._layout:
            y -= h
            child.drawOn(c, self.padding, y)
            y -= self.gap
        c.restoreState()


class MetricCard(Flowable):
    def __init__(self, label: str, value: int, accent, sublabel: str = "", width: float = 38 * mm):
        super().__init__()
        self.label = label
        self.value = value
        self.accent = accent
        self.sublabel = sublabel
        self.card_width = width

    def wrap(self, availWidth, availHeight):
        self.width = min(self.card_width, availWidth)
        self.height = 31 * mm
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.saveState()
        c.setFillColor(WHITE)
        c.setStrokeColor(LINE)
        c.setLineWidth(0.6)
        c.roundRect(0, 0, self.width, self.height, 9, fill=1, stroke=1)
        c.setFillColor(self.accent)
        c.roundRect(0, self.height - 4, self.width, 4, 2, fill=1, stroke=0)
        c.setFont(FONT_REGULAR, 8.5)
        c.setFillColor(MUTED)
        c.drawString(9, self.height - 16, self.label)
        c.setFont(FONT_BOLD, 22)
        c.setFillColor(INK)
        c.drawString(9, self.height - 39, str(self.value))
        c.setFont(FONT_REGULAR, 7)
        c.setFillColor(MUTED)
        c.drawRightString(self.width - 9, self.height - 37, "/ 100")
        if self.sublabel:
            c.setFont(FONT_REGULAR, 6.8)
            c.setFillColor(self.accent)
            c.drawString(9, 8, self.sublabel)
        c.restoreState()


class ScoreRing(Flowable):
    def __init__(self, score: int, label: str, size: float = 50 * mm):
        super().__init__()
        self.score = max(0, min(100, score))
        self.label = label
        self.size = size

    def wrap(self, availWidth, availHeight):
        self.width = self.height = min(self.size, availWidth, availHeight)
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.saveState()
        cx = self.width / 2
        cy = self.height / 2 + 3
        radius = self.width * 0.37
        c.setLineWidth(8)
        c.setStrokeColor(colors.Color(1, 1, 1, alpha=0.14))
        c.circle(cx, cy, radius, stroke=1, fill=0)
        c.setStrokeColor(ACCENT)
        extent = 360 * self.score / 100
        c.arc(cx - radius, cy - radius, cx + radius, cy + radius, startAng=90, extent=-extent)
        c.setFont(FONT_BOLD, 29)
        c.setFillColor(WHITE)
        c.drawCentredString(cx, cy - 7, str(self.score))
        c.setFont(FONT_REGULAR, 8)
        c.setFillColor(colors.HexColor("#CBD5E1"))
        c.drawCentredString(cx, cy - 20, "/ 100")
        c.setFont(FONT_BOLD, 8.5)
        c.setFillColor(WHITE)
        c.drawCentredString(cx, 4, self.label)
        c.restoreState()


class ScoreBars(Flowable):
    def __init__(self, risk: int, evidence: int, width: float):
        super().__init__()
        self.risk = max(0, min(100, risk))
        self.evidence = max(0, min(100, evidence))
        self.card_width = width

    def wrap(self, availWidth, availHeight):
        self.width = min(self.card_width, availWidth)
        self.height = 24 * mm
        return self.width, self.height

    def _draw_bar(self, c, y, label, value, fill):
        c.setFont(FONT_REGULAR, 7.5)
        c.setFillColor(MUTED)
        c.drawString(0, y + 6, label)
        c.setFont(FONT_BOLD, 7.5)
        c.setFillColor(INK)
        c.drawRightString(self.width, y + 6, f"{value}/100")
        c.setFillColor(colors.HexColor("#E5E7EB"))
        c.roundRect(0, y - 2, self.width, 5, 2.5, fill=1, stroke=0)
        c.setFillColor(fill)
        c.roundRect(0, y - 2, self.width * value / 100, 5, 2.5, fill=1, stroke=0)

    def draw(self):
        c = self.canv
        c.saveState()
        risk_color = RED if self.risk >= 76 else ACCENT if self.risk >= 56 else AMBER if self.risk >= 31 else GREEN
        self._draw_bar(c, self.height - 12, "追问风险", self.risk, risk_color)
        self._draw_bar(c, 7, "证据完整度", self.evidence, TEAL)
        c.restoreState()


class RiskDistribution(Flowable):
    def __init__(self, claims: list[ClaimAudit], width: float):
        super().__init__()
        self.claims = claims
        self.card_width = width

    def wrap(self, availWidth, availHeight):
        self.width = min(self.card_width, availWidth)
        self.height = 34 * mm
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.saveState()
        counts = {"严重": 0, "高": 0, "中": 0, "低": 0}
        for claim in self.claims:
            counts[claim.risk_level] = counts.get(claim.risk_level, 0) + 1
        total = max(1, sum(counts.values()))
        c.setFont(FONT_BOLD, 9)
        c.setFillColor(INK)
        c.drawString(0, self.height - 9, "风险分布")
        x = 0
        y = self.height - 25
        h = 8
        segments = [("严重", RED), ("高", ACCENT), ("中", colors.HexColor("#EAB308")), ("低", GREEN)]
        for name, color in segments:
            w = self.width * counts[name] / total
            if w > 0:
                c.setFillColor(color)
                c.roundRect(x, y, w, h, 4 if x == 0 or x + w >= self.width - 0.5 else 0, fill=1, stroke=0)
            x += w
        legend_y = 7
        x = 0
        for name, color in segments:
            c.setFillColor(color)
            c.circle(x + 3, legend_y + 2.5, 2.5, fill=1, stroke=0)
            c.setFont(FONT_REGULAR, 7)
            c.setFillColor(MUTED)
            c.drawString(x + 9, legend_y, f"{name} {counts[name]}")
            x += 33 * mm
        c.restoreState()


class PriorityMatrix(Flowable):
    def __init__(self, claims: list[ClaimAudit], width: float):
        super().__init__()
        self.claims = claims[:8]
        self.card_width = width

    def wrap(self, availWidth, availHeight):
        self.width = min(self.card_width, availWidth)
        self.height = 55 * mm
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.saveState()
        left, bottom = 21, 17
        plot_w, plot_h = self.width - 32, self.height - 28
        c.setFillColor(SURFACE)
        c.roundRect(left, bottom, plot_w, plot_h, 8, fill=1, stroke=0)
        c.setStrokeColor(LINE)
        c.setLineWidth(0.6)
        c.line(left + plot_w / 2, bottom, left + plot_w / 2, bottom + plot_h)
        c.line(left, bottom + plot_h / 2, left + plot_w, bottom + plot_h / 2)
        c.setFont(FONT_REGULAR, 6.5)
        c.setFillColor(MUTED)
        c.drawString(left, 5, "证据弱")
        c.drawRightString(left + plot_w, 5, "证据强")
        c.saveState()
        c.translate(7, bottom)
        c.rotate(90)
        c.drawString(0, 0, "风险低")
        c.drawRightString(plot_h, 0, "风险高")
        c.restoreState()
        for idx, claim in enumerate(self.claims, 1):
            x = left + plot_w * claim.evidence_score / 100
            # Tiny visual jitter prevents identical evidence scores from fully overlapping.
            x += ((idx - 1) % 3 - 1) * 3.2
            x = max(left + 4, min(left + plot_w - 4, x))
            y = bottom + plot_h * claim.risk_score / 100
            color = RISK_STYLE.get(claim.risk_level, (MUTED, SURFACE, ""))[0]
            c.setFillColor(color)
            c.circle(x, y, 5, fill=1, stroke=0)
            c.setFont(FONT_BOLD, 5.7)
            c.setFillColor(WHITE)
            c.drawCentredString(x, y - 2, str(idx))
        c.restoreState()


def _styles():
    base = getSampleStyleSheet()
    return {
        "cover_kicker": ParagraphStyle(
            "CoverKicker", parent=base["BodyText"], fontName=FONT_BOLD,
            fontSize=8, leading=11, textColor=colors.HexColor("#FDBA74"),
            spaceAfter=5, tracking=1.2,
        ),
        "cover_title": ParagraphStyle(
            "CoverTitle", parent=base["Title"], fontName=FONT_BOLD,
            fontSize=31, leading=39, textColor=WHITE, alignment=TA_LEFT,
            spaceAfter=8,
        ),
        "cover_sub": ParagraphStyle(
            "CoverSub", parent=base["BodyText"], fontName=FONT_REGULAR,
            fontSize=11, leading=18, textColor=colors.HexColor("#CBD5E1"),
        ),
        "cover_meta": ParagraphStyle(
            "CoverMeta", parent=base["BodyText"], fontName=FONT_REGULAR,
            fontSize=8.3, leading=14, textColor=colors.HexColor("#94A3B8"),
        ),
        "cover_summary": ParagraphStyle(
            "CoverSummary", parent=base["BodyText"], fontName=FONT_REGULAR,
            fontSize=9.3, leading=15.5, textColor=colors.HexColor("#E2E8F0"),
        ),
        "eyebrow": ParagraphStyle(
            "Eyebrow", parent=base["BodyText"], fontName=FONT_BOLD,
            fontSize=7.2, leading=10, textColor=ACCENT, tracking=1.1,
            spaceAfter=3,
        ),
        "h1": ParagraphStyle(
            "H1", parent=base["Heading1"], fontName=FONT_BOLD,
            fontSize=20, leading=27, textColor=INK, spaceBefore=4, spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "H2", parent=base["Heading2"], fontName=FONT_BOLD,
            fontSize=12.5, leading=18, textColor=INK, spaceBefore=8, spaceAfter=5,
        ),
        "h3": ParagraphStyle(
            "H3", parent=base["Heading3"], fontName=FONT_BOLD,
            fontSize=9.5, leading=14, textColor=INK, spaceBefore=5, spaceAfter=3,
        ),
        "body": ParagraphStyle(
            "Body", parent=base["BodyText"], fontName=FONT_REGULAR,
            fontSize=9.1, leading=15.2, textColor=INK_2,
        ),
        "body_small": ParagraphStyle(
            "BodySmall", parent=base["BodyText"], fontName=FONT_REGULAR,
            fontSize=7.8, leading=12.3, textColor=MUTED,
        ),
        "body_bold": ParagraphStyle(
            "BodyBold", parent=base["BodyText"], fontName=FONT_BOLD,
            fontSize=9.1, leading=14.5, textColor=INK,
        ),
        "quote": ParagraphStyle(
            "Quote", parent=base["BodyText"], fontName=FONT_SERIF,
            fontSize=10, leading=17, textColor=INK,
        ),
        "question": ParagraphStyle(
            "Question", parent=base["BodyText"], fontName=FONT_REGULAR,
            fontSize=8.6, leading=14.2, textColor=INK_2,
        ),
        "label": ParagraphStyle(
            "Label", parent=base["BodyText"], fontName=FONT_BOLD,
            fontSize=7.4, leading=10, textColor=MUTED,
        ),
        "white_small": ParagraphStyle(
            "WhiteSmall", parent=base["BodyText"], fontName=FONT_REGULAR,
            fontSize=8.2, leading=13, textColor=WHITE,
        ),
    }


def _section_title(kicker: str, title: str, styles: dict) -> list[Flowable]:
    return [_p(kicker.upper(), styles["eyebrow"]), _p(title, styles["h1"])]


def _risk_text(risk: int) -> str:
    if risk >= 76:
        return "高危 - 优先补证据"
    if risk >= 56:
        return "偏高 - 投递前修正"
    if risk >= 31:
        return "中等 - 准备追问"
    return "较低 - 基本稳健"


def _cover_canvas(canvas, doc):
    width, height = A4
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, 0, width, height, fill=1, stroke=0)
    # Decorative geometry; restrained, not flashy.
    canvas.setFillColor(colors.Color(0.97, 0.45, 0.09, alpha=0.10))
    canvas.circle(width + 18 * mm, height - 5 * mm, 58 * mm, fill=1, stroke=0)
    canvas.setFillColor(colors.Color(0.06, 0.46, 0.43, alpha=0.10))
    canvas.circle(-8 * mm, 15 * mm, 43 * mm, fill=1, stroke=0)
    canvas.setStrokeColor(colors.Color(1, 1, 1, alpha=0.07))
    canvas.setLineWidth(0.7)
    for i in range(6):
        canvas.line(0, 15 * mm + i * 12 * mm, width, 50 * mm + i * 12 * mm)
    canvas.restoreState()


def _body_canvas(canvas, doc):
    width, height = A4
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, height - 10 * mm, width, 10 * mm, fill=1, stroke=0)
    canvas.setFillColor(ACCENT)
    canvas.rect(16 * mm, height - 10 * mm, 18 * mm, 1.4 * mm, fill=1, stroke=0)
    canvas.setFont(FONT_BOLD, 7.2)
    canvas.setFillColor(colors.HexColor("#CBD5E1"))
    canvas.drawString(16 * mm, height - 6.6 * mm, "RESUMEGRILL CN  ·  EVIDENCE-BASED RESUME AUDIT")
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(16 * mm, 12 * mm, width - 16 * mm, 12 * mm)
    canvas.setFont(FONT_REGULAR, 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(16 * mm, 7.7 * mm, "本报告只识别证据缺口与追问风险，不构成诚信结论")
    canvas.drawRightString(width - 16 * mm, 7.7 * mm, f"{canvas.getPageNumber():02d}")
    canvas.restoreState()


def _claim_intro(index: int, claim: ClaimAudit, usable_width: float, styles: dict) -> list[Flowable]:
    risk_color, risk_bg, risk_en = RISK_STYLE.get(claim.risk_level, (MUTED, SURFACE, "RISK"))
    title_row = Table(
        [[
            Paragraph(f'<font color="#FFFFFF"><b>{index:02d}</b></font>', styles["body_bold"]),
            _p(claim.category, styles["body_bold"]),
            Paragraph(f'<font color="{risk_color.hexval()}"><b>{claim.risk_level}风险 · {risk_en}</b></font>', styles["body_small"]),
        ]],
        colWidths=[13 * mm, usable_width - 57 * mm, 44 * mm],
    )
    title_row.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), risk_color),
        ("BACKGROUND", (1, 0), (1, 0), WHITE),
        ("BACKGROUND", (2, 0), (2, 0), risk_bg),
        ("BOX", (0, 0), (-1, -1), 0.7, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, 0), "CENTER"),
        ("ALIGN", (2, 0), (2, 0), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    quote = RoundedCard(
        [_p("简历原文", styles["label"]), _p(claim.claim, styles["quote"])],
        usable_width,
        bg=SURFACE,
        border=LINE,
        padding=11,
        radius=10,
        gap=5,
        left_accent=risk_color,
    )
    bars = ScoreBars(claim.risk_score, claim.evidence_score, usable_width)
    return [CondPageBreak(150 * mm), title_row, Spacer(1, 4 * mm), quote, Spacer(1, 3 * mm), bars]


def generate_pdf(report: AuditReport) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=18 * mm,
        bottomMargin=17 * mm,
        title="AI简历拷打报告 - 高级版",
        author="ResumeGrill CN",
        subject="本地隐私优先的简历证据与追问风险审计",
    )
    styles = _styles()
    usable_width = A4[0] - 32 * mm
    story: list[Flowable] = []

    # ------------------------------------------------------------------
    # Cover
    # ------------------------------------------------------------------
    story.append(Spacer(1, 17 * mm))
    story.append(_p("RESUMEGRILL CN · PRIVATE AUDIT REPORT", styles["cover_kicker"]))
    story.append(_p("AI 简历拷打报告", styles["cover_title"]))
    story.append(_p("从简历声明出发，审计证据缺口、量化可信度与真实面试追问风险。", styles["cover_sub"]))
    story.append(Spacer(1, 12 * mm))

    cover_left = [
        _p("本次审计对象", styles["cover_kicker"]),
        _p(report.resume_name, ParagraphStyle(
            "CoverName", parent=styles["cover_sub"], fontName=FONT_BOLD,
            fontSize=14, leading=20, textColor=WHITE,
        )),
        Spacer(1, 5 * mm),
        _p(f"生成时间　{report.generated_at}<br/>分析引擎　{report.model_used}<br/>隐私模式　{report.privacy_mode}", styles["cover_meta"]),
        Spacer(1, 9 * mm),
        _p(report.summary, styles["cover_summary"]),
    ]
    cover_left_card = RoundedCard(
        cover_left,
        usable_width * 0.59,
        bg=colors.Color(1, 1, 1, alpha=0.055),
        border=colors.Color(1, 1, 1, alpha=0.12),
        padding=14,
        radius=13,
        gap=3,
    )
    cover_table = Table(
        [[cover_left_card, ScoreRing(report.overall_score, "抗追问综合分", 55 * mm)]],
        colWidths=[usable_width * 0.64, usable_width * 0.36],
    )
    cover_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(cover_table)
    story.append(Spacer(1, 14 * mm))

    privacy_card = RoundedCard(
        [
            _p("隐私优先 · LOCAL FIRST", styles["cover_kicker"]),
            _p("开发者看不到你上传的简历。无作者服务器、无账号系统、无后台数据库、无遥测；使用 Ollama 时内容不离开本机。", styles["white_small"]),
        ],
        usable_width,
        bg=colors.Color(0.02, 0.47, 0.42, alpha=0.18),
        border=colors.Color(0.19, 0.78, 0.68, alpha=0.35),
        padding=12,
        radius=11,
        gap=4,
    )
    story.append(privacy_card)
    story.append(PageBreak())

    # ------------------------------------------------------------------
    # Executive overview
    # ------------------------------------------------------------------
    story.extend(_section_title("01 · Executive Summary", "审计总览", styles))
    metrics = [
        MetricCard("抗追问分", report.overall_score, TEAL, "越高越稳健"),
        MetricCard("证据完整度", report.evidence_score, colors.HexColor("#2563EB"), "代码 / 日志 / 链接"),
        MetricCard("量化可信度", report.metric_score, colors.HexColor("#7C3AED"), "数字是否可复现"),
        MetricCard("疑似夸大风险", report.exaggeration_risk, RED, _risk_text(report.exaggeration_risk)),
    ]
    metric_table = Table([metrics], colWidths=[usable_width / 4] * 4)
    metric_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(metric_table)
    story.append(Spacer(1, 6 * mm))

    summary_card = RoundedCard(
        [_p("核心结论", styles["h3"]), _p(report.summary, styles["body"]), _p(report.disclaimer, styles["body_small"])],
        usable_width,
        bg=ACCENT_SOFT,
        border=colors.HexColor("#FED7AA"),
        padding=12,
        radius=11,
        gap=5,
        left_accent=ACCENT,
    )
    story.append(summary_card)
    story.append(Spacer(1, 6 * mm))

    distribution = RiskDistribution(report.claims, usable_width * 0.47)
    matrix = PriorityMatrix(report.claims, usable_width * 0.47)
    overview_table = Table([[distribution, matrix]], colWidths=[usable_width * 0.49, usable_width * 0.51])
    overview_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, 0), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 8),
        ("LEFTPADDING", (1, 0), (1, 0), 8),
        ("RIGHTPADDING", (1, 0), (1, 0), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(overview_table)
    story.append(Spacer(1, 5 * mm))

    story.append(_p("优先处理事项", styles["h2"]))
    flags = report.global_flags or ["暂未发现全局风险提示。"]
    flag_cols = []
    for flag in flags[:4]:
        flag_cols.append(RoundedCard([
            _p(flag, styles["body"])
        ], usable_width / 2 - 4 * mm, bg=WHITE, border=LINE, padding=10, radius=9, left_accent=AMBER))
    while len(flag_cols) % 2:
        flag_cols.append(Spacer(1, 1))
    rows = [flag_cols[i:i + 2] for i in range(0, len(flag_cols), 2)]
    if rows:
        flag_table = Table(rows, colWidths=[usable_width / 2] * 2)
        flag_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(flag_table)

    story.append(PageBreak())

    # ------------------------------------------------------------------
    # Claims
    # ------------------------------------------------------------------
    story.extend(_section_title("02 · Claim-by-Claim Audit", "逐条声明审计", styles))
    story.append(_p("以下内容按风险从高到低排列。高风险不等于造假，而是意味着面试官更可能要求你当场给出证据、边界和复现细节。", styles["body"]))
    story.append(Spacer(1, 5 * mm))

    for idx, claim in enumerate(report.claims, 1):
        story.extend(_claim_intro(idx, claim, usable_width, styles))
        story.append(Spacer(1, 3 * mm))

        # Signals and evidence gaps in two columns.
        signal_items = claim.flags or ["暂未发现明显风险信号"]
        gap_items = claim.missing_evidence or ["当前无需额外补证据"]
        signal_children: list[Flowable] = [_p("风险信号", styles["h3"])]
        signal_children += [_bullet(x, styles["body_small"], "#B91C1C") for x in signal_items]
        gap_children: list[Flowable] = [_p("建议补齐的证据", styles["h3"])]
        gap_children += [_bullet(x, styles["body_small"], "#0F766E") for x in gap_items]
        left_card = RoundedCard(signal_children, usable_width / 2 - 4 * mm, bg=RED_SOFT, border=colors.HexColor("#FECACA"), padding=10, radius=9, gap=3)
        right_card = RoundedCard(gap_children, usable_width / 2 - 4 * mm, bg=TEAL_SOFT, border=colors.HexColor("#99F6E4"), padding=10, radius=9, gap=3)
        two_col = Table([[left_card, right_card]], colWidths=[usable_width / 2] * 2)
        two_col.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (0, 0), 0),
            ("RIGHTPADDING", (0, 0), (0, 0), 4),
            ("LEFTPADDING", (1, 0), (1, 0), 4),
            ("RIGHTPADDING", (1, 0), (1, 0), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(two_col)

        if claim.evidence.files or claim.evidence.notes:
            story.append(Spacer(1, 4 * mm))
            evidence_parts: list[Flowable] = [_p("仓库证据快照", styles["h3"])]
            if claim.evidence.files:
                evidence_parts.append(_p("匹配文件：" + "、".join(claim.evidence.files[:8]), styles["body_small"]))
            for note in claim.evidence.notes[:4]:
                evidence_parts.append(_bullet(note, styles["body_small"], "#2563EB"))
            story.append(RoundedCard(evidence_parts, usable_width, bg=colors.HexColor("#EFF6FF"), border=colors.HexColor("#BFDBFE"), padding=10, radius=9, gap=3, left_accent=colors.HexColor("#2563EB")))

        story.append(Spacer(1, 4 * mm))
        story.append(_p("面试官可能怎么追问", styles["h2"]))
        q_rows = []
        for q_idx, q in enumerate(claim.questions, 1):
            q_rows.append([
                Paragraph(f'<font color="#F97316"><b>{q_idx:02d}</b></font>', styles["body_bold"]),
                _p(q, styles["question"]),
            ])
        if q_rows:
            q_table = Table(q_rows, colWidths=[12 * mm, usable_width - 12 * mm], repeatRows=0)
            q_table.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -2), 0.4, LINE),
                ("LEFTPADDING", (0, 0), (0, -1), 2),
                ("RIGHTPADDING", (0, 0), (0, -1), 6),
                ("LEFTPADDING", (1, 0), (1, -1), 3),
                ("RIGHTPADDING", (1, 0), (1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]))
            story.append(q_table)
        story.append(Spacer(1, 9 * mm))

    story.append(PageBreak())

    # ------------------------------------------------------------------
    # Action plan
    # ------------------------------------------------------------------
    story.extend(_section_title("03 · Defense Plan", "投递前修复路线", styles))
    story.append(_p("不要为了降低风险而删除所有亮点。正确做法是让每个重要结论都能回到一条可核验的证据链。", styles["body"]))
    story.append(Spacer(1, 5 * mm))

    steps = [
        ("01", "先处理红色声明", "从严重风险开始：补 baseline、实验设置、原始日志和责任边界。"),
        ("02", "建立证据目录", "为每个数字保留 README、命令、配置、结果表、截图或官方链接。"),
        ("03", "降低过满措辞", "无法解释底层原理的技术，用‘使用过’‘熟悉’替代‘精通’。"),
        ("04", "准备 60 秒项目陈述", "按问题-方法-本人贡献-结果-限制的顺序组织，不要堆技术名词。"),
        ("05", "做一次压力问答", "让同学连续追问代码位置、对照实验和失败案例，直到回答可复现。"),
    ]
    for number, title, text in steps:
        number_box = Table([[Paragraph(f'<font color="#FFFFFF"><b>{number}</b></font>', styles["body_bold"])]], colWidths=[13 * mm], rowHeights=[13 * mm])
        number_box.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), NAVY),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOX", (0, 0), (-1, -1), 0, NAVY),
        ]))
        text_card = RoundedCard([_p(title, styles["body_bold"]), _p(text, styles["body_small"])], usable_width - 18 * mm, bg=WHITE, border=LINE, padding=9, radius=8, gap=2)
        row = Table([[number_box, text_card]], colWidths=[17 * mm, usable_width - 17 * mm])
        row.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        story.append(row)
        story.append(Spacer(1, 2 * mm))

    story.append(Spacer(1, 6 * mm))
    story.append(_p("面试前证据清单", styles["h2"]))
    checklist = [
        "每个精确数字都有原始日志、结果表或可复现命令。",
        "写清 baseline、数据划分、硬件、随机种子、测试次数与误差范围。",
        "明确本人贡献、团队贡献和引用的开源工作。",
        "论文、竞赛、证书和排名提供官方链接、DOI或编号。",
        "GitHub README 包含环境、运行步骤、结果、限制与失败案例。",
        "所有写进‘技能’的内容，都至少能解释用途、边界和一个真实问题。",
    ]
    check_rows = []
    for item in checklist:
        check_rows.append([
            Paragraph('<font color="#0F766E">□</font>', styles["body_bold"]),
            _p(item, styles["body"]),
        ])
    check_table = Table(check_rows, colWidths=[9 * mm, usable_width - 9 * mm])
    check_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, -1), SURFACE),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(check_table)
    story.append(Spacer(1, 6 * mm))

    boundary_card = RoundedCard(
        [
            _p("隐私与判断边界", styles["h3"]),
            _p("开发者无法看到、接收或保存用户上传的简历。项目默认使用规则引擎或本机 Ollama，不执行上传仓库代码，只做静态文本与 Git 历史分析。", styles["body"]),
            _p("本报告不是背景调查、学历认证或法律意义上的诚信结论。疑似夸大仅表示证据不足、表述矛盾或面试追问风险较高。", styles["body_small"]),
        ],
        usable_width,
        bg=GREEN_SOFT,
        border=colors.HexColor("#A7F3D0"),
        padding=12,
        radius=11,
        gap=5,
        left_accent=GREEN,
    )
    story.append(boundary_card)

    doc.build(story, onFirstPage=_cover_canvas, onLaterPages=_body_canvas)
    return buffer.getvalue()
