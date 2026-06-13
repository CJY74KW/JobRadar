"""
pdf_report.py
채용공고 분석 결과와 AI 지원 준비 내용을 PDF 보고서로 저장한다.
"""

from __future__ import annotations

import os
import textwrap
from collections import Counter
from datetime import datetime
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont


PAGE_WIDTH = 1240
PAGE_HEIGHT = 1754
MARGIN_X = 90
MARGIN_TOP = 80
MARGIN_BOTTOM = 90
CONTENT_WIDTH = PAGE_WIDTH - (MARGIN_X * 2)

COLOR_TEXT = "#111827"
COLOR_MUTED = "#6B7280"
COLOR_LINE = "#DDE3EE"
COLOR_BLUE = "#4F6BED"
COLOR_BLUE_DARK = "#1F4E79"
COLOR_BG = "#FFFFFF"
COLOR_SOFT = "#F3F6FB"

FONT_PATHS = [
    r"C:\Windows\Fonts\malgun.ttf",
    r"C:\Windows\Fonts\malgunbd.ttf",
    r"C:\Windows\Fonts\NanumGothic.ttf",
]


def save_search_pdf_report(jobs: list[dict], tech_stats: list[tuple],
                           chart_data: dict, path: str,
                           search_params: dict | None = None) -> None:
    """검색 결과 전체를 요약한 PDF 보고서를 저장한다."""
    builder = _PdfBuilder("채용공고 검색 결과 보고서")
    sorted_jobs = sorted(jobs, key=lambda j: _safe_score(j.get("score")), reverse=True)
    search_params = search_params or {}

    builder.title("채용공고 검색 결과 보고서")
    builder.meta(f"생성일: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    tech_stack = search_params.get("tech_stack") or search_params.get("tech_stack_raw") or ""
    if isinstance(tech_stack, list):
        tech_stack = ", ".join(tech_stack)

    summary_rows = [
        ("총 매칭 공고", f"{len(sorted_jobs)}개"),
        ("검색 기술 스택", tech_stack or "-"),
        ("평균 적합도", f"{_average_score(sorted_jobs):.1f}점" if sorted_jobs else "-"),
        ("최고 적합도", f"{_safe_score(sorted_jobs[0].get('score')):.1f}점" if sorted_jobs else "-"),
    ]
    builder.section("1. 검색 요약")
    builder.key_values(summary_rows)

    builder.section("2. 기술 키워드 수요 현황")
    tech_rows = _normalise_stats(tech_stats, limit=15)
    if tech_rows:
        builder.bar_chart(tech_rows, max_items=15)
    else:
        builder.paragraph("수집된 기술 키워드 통계가 없습니다.")

    builder.section("3. 대시보드 요약")
    score_rows = _score_rows(chart_data, sorted_jobs)
    source_rows = _source_rows(chart_data, sorted_jobs)
    builder.small_table("적합도 점수 분포", score_rows)
    builder.small_table("수집 출처별 공고 수", source_rows)

    builder.section("4. 점수 상위 공고")
    if not sorted_jobs:
        builder.paragraph("입력한 기술 스택이 포함된 공고가 없습니다.")
    for idx, job in enumerate(sorted_jobs[:15], 1):
        builder.job_card(idx, job)

    builder.save(path)


def save_job_ai_pdf_report(job: dict, cover_letter_points: list[str],
                           interview_questions: list[str], path: str) -> None:
    """공고 1건에 대한 AI 지원 준비 PDF 보고서를 저장한다."""
    builder = _PdfBuilder("지원 준비 PDF 보고서")
    builder.title("지원 준비 PDF 보고서")
    builder.meta(f"생성일: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    builder.section("1. 공고 기본 정보")
    builder.key_values([
        ("회사명", job.get("company", "-")),
        ("공고명", job.get("title", "-")),
        ("근무지", job.get("location", "-")),
        ("적합도 점수", f"{job.get('score', '-')}점"),
        ("기술 키워드", _join_values(job.get("tech_keywords", [])) or "-"),
        ("공고 링크", job.get("link", "-")),
    ])

    builder.section("2. 적합도 분석")
    if job.get("score_breakdown"):
        for key, label in [
            ("tech", "기술"),
            ("role", "직무"),
            ("region", "지역"),
            ("quality", "정보"),
        ]:
            part = job.get("score_breakdown", {}).get(key)
            if not part:
                continue
            builder.bullet(
                f"{label}: {part.get('score', 0)}/{part.get('max', 0)} - {part.get('label', '')}"
            )
    elif job.get("match_detail"):
        builder.paragraph(str(job.get("match_detail")))
    else:
        builder.paragraph("적합도 세부 분석 데이터가 없습니다.")

    builder.section("3. 자기소개서 작성 포인트")
    builder.bullets(cover_letter_points or ["생성된 자기소개서 포인트가 없습니다."])

    builder.section("4. 예상 면접 질문")
    if interview_questions:
        for idx, question in enumerate(interview_questions, 1):
            builder.bullet(f"Q{idx}. {question}")
    else:
        builder.paragraph("생성된 예상 면접 질문이 없습니다.")

    builder.section("5. 지원 전략 요약")
    builder.bullets(_build_strategy_points(job, cover_letter_points))

    builder.save(path)


class _PdfBuilder:
    def __init__(self, title: str):
        self.title_text = title
        self.pages: list[Image.Image] = []
        self.font_regular = _load_font(30)
        self.font_bold = _load_font(34, bold=True)
        self.font_title = _load_font(50, bold=True)
        self.font_section = _load_font(34, bold=True)
        self.font_small = _load_font(24)
        self.font_small_bold = _load_font(24, bold=True)
        self._new_page()

    def _new_page(self) -> None:
        self.image = Image.new("RGB", (PAGE_WIDTH, PAGE_HEIGHT), COLOR_BG)
        self.draw = ImageDraw.Draw(self.image)
        self.y = MARGIN_TOP
        self.pages.append(self.image)

    def _ensure(self, height: int) -> None:
        if self.y + height > PAGE_HEIGHT - MARGIN_BOTTOM:
            self._footer()
            self._new_page()

    def _footer(self) -> None:
        page_no = len(self.pages)
        self.draw.line(
            (MARGIN_X, PAGE_HEIGHT - 65, PAGE_WIDTH - MARGIN_X, PAGE_HEIGHT - 65),
            fill=COLOR_LINE,
            width=1,
        )
        self.draw.text(
            (MARGIN_X, PAGE_HEIGHT - 48),
            self.title_text,
            font=self.font_small,
            fill=COLOR_MUTED,
        )
        page_text = f"{page_no}"
        page_w = self.draw.textlength(page_text, font=self.font_small)
        self.draw.text(
            (PAGE_WIDTH - MARGIN_X - page_w, PAGE_HEIGHT - 48),
            page_text,
            font=self.font_small,
            fill=COLOR_MUTED,
        )

    def title(self, text: str) -> None:
        self._ensure(90)
        self.draw.text((MARGIN_X, self.y), text, font=self.font_title, fill=COLOR_BLUE_DARK)
        self.y += 72

    def meta(self, text: str) -> None:
        self.draw.text((MARGIN_X, self.y), text, font=self.font_small, fill=COLOR_MUTED)
        self.y += 46

    def section(self, text: str) -> None:
        self._ensure(90)
        self.y += 18
        self.draw.rectangle((MARGIN_X, self.y + 8, MARGIN_X + 8, self.y + 46), fill=COLOR_BLUE)
        self.draw.text((MARGIN_X + 20, self.y), text, font=self.font_section, fill=COLOR_TEXT)
        self.y += 64

    def paragraph(self, text: str) -> None:
        lines = _wrap_text(str(text), self.font_regular, CONTENT_WIDTH, self.draw)
        self._ensure(max(45, len(lines) * 40 + 14))
        for line in lines:
            self.draw.text((MARGIN_X, self.y), line, font=self.font_regular, fill=COLOR_TEXT)
            self.y += 40
        self.y += 14

    def bullet(self, text: str) -> None:
        self.bullets([text])

    def bullets(self, values: Iterable[str]) -> None:
        for value in values:
            text = str(value or "").strip()
            if not text:
                continue
            lines = _wrap_text(text, self.font_regular, CONTENT_WIDTH - 34, self.draw)
            self._ensure(max(44, len(lines) * 38 + 10))
            self.draw.ellipse((MARGIN_X, self.y + 13, MARGIN_X + 9, self.y + 22), fill=COLOR_BLUE)
            for idx, line in enumerate(lines):
                self.draw.text(
                    (MARGIN_X + 28, self.y),
                    line,
                    font=self.font_regular,
                    fill=COLOR_TEXT,
                )
                self.y += 38
            self.y += 8

    def key_values(self, rows: list[tuple[str, str]]) -> None:
        row_h = 54
        self._ensure(row_h * len(rows) + 20)
        for idx, (key, value) in enumerate(rows):
            y1 = self.y
            fill = COLOR_SOFT if idx % 2 == 0 else COLOR_BG
            self.draw.rectangle((MARGIN_X, y1, PAGE_WIDTH - MARGIN_X, y1 + row_h), fill=fill)
            self.draw.text((MARGIN_X + 18, y1 + 12), str(key), font=self.font_small_bold, fill=COLOR_BLUE_DARK)
            value_lines = _wrap_text(str(value), self.font_small, CONTENT_WIDTH - 300, self.draw)
            self.draw.text((MARGIN_X + 290, y1 + 12), value_lines[0] if value_lines else "", font=self.font_small, fill=COLOR_TEXT)
            self.y += row_h
        self.y += 20

    def bar_chart(self, rows: list[tuple[str, int]], max_items: int = 15) -> None:
        rows = rows[:max_items]
        if not rows:
            return
        max_value = max(value for _, value in rows) or 1
        row_h = 48
        self._ensure(row_h * len(rows) + 36)
        label_w = 220
        chart_w = CONTENT_WIDTH - label_w - 90
        for label, value in rows:
            label_lines = _wrap_text(label, self.font_small, label_w - 10, self.draw)
            self.draw.text((MARGIN_X, self.y + 8), label_lines[0] if label_lines else label, font=self.font_small, fill=COLOR_TEXT)
            bar_x = MARGIN_X + label_w
            bar_y = self.y + 9
            self.draw.rounded_rectangle((bar_x, bar_y, bar_x + chart_w, bar_y + 28), radius=8, fill="#EDF1F7")
            width = int(chart_w * (value / max_value))
            self.draw.rounded_rectangle((bar_x, bar_y, bar_x + width, bar_y + 28), radius=8, fill=COLOR_BLUE)
            self.draw.text((bar_x + width + 12, self.y + 5), f"{value}개", font=self.font_small, fill=COLOR_BLUE_DARK)
            self.y += row_h
        self.y += 22

    def small_table(self, title: str, rows: list[tuple[str, int]]) -> None:
        rows = rows or []
        self._ensure(68 + (len(rows) + 1) * 44)
        self.draw.text((MARGIN_X, self.y), title, font=self.font_small_bold, fill=COLOR_TEXT)
        self.y += 42
        for label, value in rows:
            self.draw.line((MARGIN_X, self.y, PAGE_WIDTH - MARGIN_X, self.y), fill=COLOR_LINE, width=1)
            self.draw.text((MARGIN_X + 10, self.y + 10), str(label), font=self.font_small, fill=COLOR_TEXT)
            text = f"{value}개"
            text_w = self.draw.textlength(text, font=self.font_small)
            self.draw.text((PAGE_WIDTH - MARGIN_X - text_w - 10, self.y + 10), text, font=self.font_small, fill=COLOR_BLUE_DARK)
            self.y += 44
        self.draw.line((MARGIN_X, self.y, PAGE_WIDTH - MARGIN_X, self.y), fill=COLOR_LINE, width=1)
        self.y += 26

    def job_card(self, rank: int, job: dict) -> None:
        card_h = 230
        self._ensure(card_h + 26)
        x1, y1 = MARGIN_X, self.y
        x2, y2 = PAGE_WIDTH - MARGIN_X, y1 + card_h
        self.draw.rounded_rectangle((x1, y1, x2, y2), radius=16, fill=COLOR_SOFT)
        self.draw.text((x1 + 24, y1 + 22), f"{rank}. {job.get('company', '-')}", font=self.font_small_bold, fill=COLOR_BLUE_DARK)
        score_text = f"{_safe_score(job.get('score')):.1f}점"
        score_w = self.draw.textlength(score_text, font=self.font_small_bold)
        self.draw.text((x2 - score_w - 24, y1 + 22), score_text, font=self.font_small_bold, fill=COLOR_BLUE)

        title_lines = _wrap_text(str(job.get("title", "-")), self.font_regular, CONTENT_WIDTH - 48, self.draw)
        self.draw.text((x1 + 24, y1 + 66), title_lines[0] if title_lines else "-", font=self.font_regular, fill=COLOR_TEXT)
        self.draw.text((x1 + 24, y1 + 110), f"근무지: {job.get('location', '-')}", font=self.font_small, fill=COLOR_MUTED)
        self.draw.text((x1 + 24, y1 + 148), f"기술 키워드: {_join_values(job.get('tech_keywords', [])) or '-'}", font=self.font_small, fill=COLOR_TEXT)

        detail = str(job.get("match_detail") or "")
        if not detail and job.get("score_breakdown"):
            detail = _score_detail_text(job.get("score_breakdown", {}))
        detail_lines = _wrap_text(detail, self.font_small, CONTENT_WIDTH - 48, self.draw)
        if detail_lines:
            self.draw.text((x1 + 24, y1 + 186), detail_lines[0], font=self.font_small, fill=COLOR_MUTED)

        self.y += card_h + 26

    def save(self, path: str) -> None:
        output_dir = os.path.dirname(path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        self._footer()
        first, rest = self.pages[0], self.pages[1:]
        first.save(path, "PDF", save_all=True, append_images=rest, resolution=150.0)


def _load_font(size: int, bold: bool = False):
    candidates = [FONT_PATHS[1], FONT_PATHS[0]] if bold else [FONT_PATHS[0], FONT_PATHS[2]]
    for path in candidates:
        if path and os.path.exists(path):
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def _wrap_text(text: str, font, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    lines: list[str] = []
    for paragraph in str(text or "").splitlines() or [""]:
        paragraph = paragraph.strip()
        if not paragraph:
            lines.append("")
            continue
        words = paragraph.split()
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if draw.textlength(candidate, font=font) <= max_width:
                current = candidate
                continue
            if current:
                lines.append(current)
            if draw.textlength(word, font=font) <= max_width:
                current = word
            else:
                chunk = ""
                for char in word:
                    if draw.textlength(chunk + char, font=font) <= max_width:
                        chunk += char
                    else:
                        if chunk:
                            lines.append(chunk)
                        chunk = char
                current = chunk
        if current:
            lines.append(current)
    return lines


def _normalise_stats(stats: list[tuple] | None, limit: int = 15) -> list[tuple[str, int]]:
    rows = []
    for name, count in stats or []:
        try:
            count_value = int(count)
        except (TypeError, ValueError):
            count_value = 0
        rows.append((str(name), count_value))
    return rows[:limit]


def _score_rows(chart_data: dict, jobs: list[dict]) -> list[tuple[str, int]]:
    score_data = chart_data.get("score", {}) if chart_data else {}
    labels = score_data.get("labels") or []
    values = score_data.get("values") or []
    if labels and values:
        return [(str(label), int(value)) for label, value in zip(labels, values)]

    bins = [("0-20", 0), ("21-40", 0), ("41-60", 0), ("61-80", 0), ("81-100", 0)]
    for job in jobs:
        score = _safe_score(job.get("score"))
        idx = 0 if score <= 20 else 1 if score <= 40 else 2 if score <= 60 else 3 if score <= 80 else 4
        label, count = bins[idx]
        bins[idx] = (label, count + 1)
    return bins


def _source_rows(chart_data: dict, jobs: list[dict]) -> list[tuple[str, int]]:
    source_data = chart_data.get("source", {}) if chart_data else {}
    labels = source_data.get("labels") or []
    values = source_data.get("values") or []
    if labels and values:
        return [(str(label), int(value)) for label, value in zip(labels, values)]
    counter = Counter(job.get("source", "기타") or "기타" for job in jobs)
    return [(name, count) for name, count in counter.most_common()]


def _average_score(jobs: list[dict]) -> float:
    if not jobs:
        return 0.0
    return sum(_safe_score(job.get("score")) for job in jobs) / len(jobs)


def _safe_score(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _join_values(values) -> str:
    if isinstance(values, str):
        return values
    if not values:
        return ""
    return ", ".join(str(value) for value in values)


def _score_detail_text(score_breakdown: dict) -> str:
    labels = {"tech": "기술", "role": "직무", "region": "지역", "quality": "정보"}
    parts = []
    for key, label in labels.items():
        part = score_breakdown.get(key)
        if part:
            parts.append(f"{label} {part.get('score', 0)}/{part.get('max', 0)}")
    return ", ".join(parts)


def _build_strategy_points(job: dict, cover_letter_points: list[str]) -> list[str]:
    keywords = _join_values(job.get("tech_keywords", []))
    points = []
    if keywords:
        points.append(f"자기소개서와 면접 답변에서 {keywords} 경험을 가장 먼저 드러내세요.")
    if job.get("requirements"):
        points.append("공고의 자격요건 문장을 기준으로 프로젝트 경험, 역할, 성과를 짧게 연결하세요.")
    if cover_letter_points:
        points.append("AI가 제안한 자기소개서 포인트 중 실제 경험으로 증명 가능한 항목을 우선 사용하세요.")
    points.append("면접 질문은 STAR 방식으로 상황, 과제, 행동, 결과 순서로 답변을 준비하세요.")
    return points
