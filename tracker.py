"""
tracker.py
지원 현황 관리 모듈 (SQLite 기반)
- 지원예정 / 지원완료 / 서류합격 / 면접 / 최종합격 / 불합격 상태 추적
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join("output", "jobs.db")

STATUSES = ["지원예정", "지원완료", "서류합격", "면접", "최종합격", "불합격"]

STATUS_COLOR = {
    "지원예정": "#64748b",
    "지원완료": "#2563eb",
    "서류합격": "#7c3aed",
    "면접":    "#d97706",
    "최종합격": "#16a34a",
    "불합격":  "#dc2626",
}


def _get_conn() -> sqlite3.Connection:
    os.makedirs("output", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_tracker_db() -> None:
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                company      TEXT    NOT NULL,
                title        TEXT    NOT NULL,
                link         TEXT    DEFAULT '',
                status       TEXT    DEFAULT '지원예정',
                applied_date TEXT    DEFAULT '',
                deadline     TEXT    DEFAULT '',
                location     TEXT    DEFAULT '',
                score        REAL    DEFAULT 0,
                notes        TEXT    DEFAULT '',
                created_at   TEXT    NOT NULL,
                updated_at   TEXT    NOT NULL
            )
        """)
        conn.commit()


def add_application(company: str, title: str, link: str = "",
                    status: str = "지원완료", deadline: str = "",
                    location: str = "", score: float = 0,
                    notes: str = "") -> int:
    """지원 공고 등록, 생성된 ID 반환"""
    init_tracker_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today = datetime.now().strftime("%Y-%m-%d")
    with _get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO applications
              (company, title, link, status, applied_date, deadline,
               location, score, notes, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (company, title, link, status, today, deadline,
             location, score, notes, now, now),
        )
        conn.commit()
        return cur.lastrowid


def get_all_applications() -> list[dict]:
    """전체 지원 목록 (최신순)"""
    init_tracker_db()
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM applications ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_applications_by_status() -> dict[str, list[dict]]:
    """상태별로 그룹핑된 지원 목록"""
    grouped = {s: [] for s in STATUSES}
    for app in get_all_applications():
        s = app.get("status", "지원예정")
        if s in grouped:
            grouped[s].append(app)
    return grouped


def update_application(app_id: int, status: str = None,
                       notes: str = None) -> bool:
    """상태 또는 메모 업데이트"""
    if status is not None and status not in STATUSES:
        return False
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _get_conn() as conn:
        if status is not None and notes is not None:
            conn.execute(
                "UPDATE applications SET status=?, notes=?, updated_at=? WHERE id=?",
                (status, notes, now, app_id),
            )
        elif status is not None:
            conn.execute(
                "UPDATE applications SET status=?, updated_at=? WHERE id=?",
                (status, now, app_id),
            )
        elif notes is not None:
            conn.execute(
                "UPDATE applications SET notes=?, updated_at=? WHERE id=?",
                (notes, now, app_id),
            )
        conn.commit()
    return True


def delete_application(app_id: int) -> bool:
    with _get_conn() as conn:
        conn.execute("DELETE FROM applications WHERE id=?", (app_id,))
        conn.commit()
    return True


def get_tracker_stats() -> dict:
    """상태별 카운트 및 전체 합계"""
    apps = get_all_applications()
    by_status = {s: 0 for s in STATUSES}
    for app in apps:
        s = app.get("status", "지원예정")
        if s in by_status:
            by_status[s] += 1
    return {
        "total":     len(apps),
        "by_status": by_status,
        "colors":    STATUS_COLOR,
    }
