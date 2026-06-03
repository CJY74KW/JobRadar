"""
storage.py
분석 결과 저장 모듈
- Excel (시트별 분리): 전체 공고, 추천 공고, 마감 임박, 기술 통계, 지원 준비
- CSV: 전체 공고 백업
- SQLite: 누적 공고 DB 저장
"""

import os
import csv
import sqlite3
import json
from datetime import datetime

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter


def save_all(jobs: list[dict], recommended: list[dict],
             deadline_soon: list[dict], tech_stats: list[tuple],
             config: dict) -> None:
    output_dir = os.path.dirname(config["output"]["excel_path"])
    os.makedirs(output_dir, exist_ok=True)

    save_csv(jobs, config["output"]["csv_path"])
    save_excel(jobs, recommended, deadline_soon, tech_stats, config)
    save_sqlite(jobs, config["output"]["db_path"])
    print(f"\n[저장 완료] 결과가 '{output_dir}' 폴더에 저장되었습니다.")


# ============================================================
# CSV 저장
# ============================================================
def save_csv(jobs: list[dict], path: str) -> None:
    if not jobs:
        return
    flat = [_flatten(j) for j in jobs]
    fieldnames = list(flat[0].keys())
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(flat)
    print(f"  CSV 저장: {path} ({len(jobs)}개)")


# ============================================================
# Excel 저장
# ============================================================
def save_excel(jobs: list[dict], recommended: list[dict],
               deadline_soon: list[dict], tech_stats: list[tuple],
               config: dict) -> None:
    path = config["output"]["excel_path"]

    # 기본 열 정의 (공고 목록 시트용)
    job_cols = ["source", "company", "title", "location", "job_type",
                "experience", "deadline", "dday", "salary", "score",
                "match_detail", "tech_keywords", "link"]

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        # 시트1: 전체 공고
        df_all = _jobs_to_df(jobs, job_cols)
        df_all.to_excel(writer, sheet_name="전체공고", index=False)

        # 시트2: 추천 공고 (점수 상위)
        df_rec = _jobs_to_df(recommended, job_cols)
        df_rec.to_excel(writer, sheet_name="추천공고", index=False)

        # 시트3: 마감 임박 공고
        df_dl = _jobs_to_df(deadline_soon, job_cols)
        df_dl.to_excel(writer, sheet_name="마감임박", index=False)

        # 시트4: 기술 키워드 통계
        if tech_stats:
            df_tech = pd.DataFrame(tech_stats, columns=["기술키워드", "공고수"])
            df_tech.to_excel(writer, sheet_name="기술키워드통계", index=False)

        # 시트5: 지원 준비 (자소서 포인트 + 면접 질문)
        prep_rows = []
        for job in recommended[:10]:
            prep_rows.append({
                "회사명": job.get("company", ""),
                "공고명": job.get("title", ""),
                "마감일": job.get("deadline", ""),
                "자기소개서 작성 포인트": "\n".join(
                    f"• {p}" for p in job.get("cover_letter_points", [])
                ),
                "예상 면접 질문": "\n".join(
                    f"Q{i+1}. {q}" for i, q in enumerate(job.get("interview_questions", []))
                ),
            })
        if prep_rows:
            df_prep = pd.DataFrame(prep_rows)
            df_prep.to_excel(writer, sheet_name="지원준비", index=False)

    _apply_excel_style(path)
    print(f"  Excel 저장: {path}")


def _jobs_to_df(jobs: list[dict], cols: list[str]) -> pd.DataFrame:
    rows = []
    for job in jobs:
        row = {}
        for col in cols:
            val = job.get(col, "")
            if isinstance(val, list):
                val = ", ".join(str(v) for v in val)
            row[col] = val
        rows.append(row)
    col_rename = {
        "source": "출처", "company": "회사명", "title": "공고명",
        "location": "근무지", "job_type": "고용형태", "experience": "경력",
        "deadline": "마감일", "dday": "D-Day", "salary": "급여",
        "score": "적합도점수", "match_detail": "매칭근거",
        "tech_keywords": "기술키워드", "link": "공고링크",
    }
    df = pd.DataFrame(rows, columns=cols)
    df.rename(columns=col_rename, inplace=True)
    return df


def _apply_excel_style(path: str) -> None:
    """헤더 강조 및 열 너비 자동 조정"""
    wb = load_workbook(path)
    header_fill = PatternFill("solid", fgColor="1F4E79")
    header_font = Font(color="FFFFFF", bold=True)
    border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )

    for ws in wb.worksheets:
        # 헤더 스타일
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", wrap_text=True)
            cell.border = border

        # 열 너비 자동 조정
        for col_idx, col in enumerate(ws.columns, 1):
            max_len = max(
                (len(str(c.value)) if c.value else 0 for c in col), default=0
            )
            ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 4, 50)

        # 지원준비 시트는 행 높이 크게
        if ws.title == "지원준비":
            for row in ws.iter_rows(min_row=2):
                ws.row_dimensions[row[0].row].height = 120
                for cell in row:
                    cell.alignment = Alignment(wrap_text=True, vertical="top")

    wb.save(path)


# ============================================================
# SQLite 저장
# ============================================================
def save_sqlite(jobs: list[dict], db_path: str) -> None:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            company TEXT,
            title TEXT,
            location TEXT,
            job_type TEXT,
            experience TEXT,
            deadline TEXT,
            dday TEXT,
            salary TEXT,
            score REAL,
            tech_keywords TEXT,
            link TEXT,
            collected_at TEXT,
            UNIQUE(company, title, deadline)
        )
    """)

    inserted = 0
    for job in jobs:
        try:
            cur.execute("""
                INSERT OR IGNORE INTO jobs
                (source, company, title, location, job_type, experience,
                 deadline, dday, salary, score, tech_keywords, link, collected_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                job.get("source", ""),
                job.get("company", ""),
                job.get("title", ""),
                job.get("location", ""),
                job.get("job_type", ""),
                job.get("experience", ""),
                job.get("deadline", ""),
                job.get("dday", ""),
                job.get("salary", ""),
                job.get("score", 0),
                ", ".join(job.get("tech_keywords", [])),
                job.get("link", ""),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ))
            if cur.rowcount:
                inserted += 1
        except sqlite3.Error:
            continue

    conn.commit()
    conn.close()
    print(f"  SQLite 저장: {db_path} (신규 {inserted}개)")


def _flatten(job: dict) -> dict:
    flat = {}
    for k, v in job.items():
        if isinstance(v, list):
            flat[k] = ", ".join(str(i) for i in v)
        elif isinstance(v, dict):
            flat[k] = json.dumps(v, ensure_ascii=False)
        else:
            flat[k] = v
    return flat
