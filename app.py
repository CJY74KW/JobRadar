"""
app.py
채용 정보 웹 애플리케이션 - Flask 백엔드
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from collections import Counter

from flask import Flask, render_template, request, redirect, url_for, jsonify, flash

from api_collector import collect_all_jobs
from data_parser   import parse_and_clean, filter_expired, filter_deadline_soon
from analyzer      import score_jobs, get_recommended, get_tech_stats
from ai_generator  import add_ai_content
from tracker       import (
    init_tracker_db, add_application, get_all_applications,
    get_applications_by_status, update_application,
    delete_application, get_tracker_stats, STATUSES, STATUS_COLOR,
)

app = Flask(__name__)
app.secret_key = "job-tracker-secret-key-2026"

# ============================================================
# 공통 상수
# ============================================================
REGION_OPTIONS     = [
    "서울", "경기", "인천", "부산", "대구", "대전",
    "광주", "울산", "강원", "충북", "충남", "전북",
    "전남", "경북", "경남", "제주", "세종",
]
JOB_TYPE_OPTIONS   = ["정규직", "계약직", "인턴", "아르바이트"]
EXPERIENCE_OPTIONS = ["신입", "경력"]
DEFAULT_TECH       = "Python, SQL, React, AWS, Django"


# ============================================================
# 헬퍼 함수
# ============================================================
def build_config(form) -> dict:
    tech_raw   = form.get("tech_stack", DEFAULT_TECH)
    tech_stack = [t.strip() for t in tech_raw.split(",") if t.strip()]
    return {
        "search": {
            "keyword":    form.get("keyword", "파이썬").strip() or "파이썬",
            "region":     form.get("region", ""),
            "job_type":   form.get("job_type", ""),
            "experience": form.get("experience", ""),
            "tech_stack": tech_stack,
        },
        "scoring": {
            "weight_job_match":    40,
            "weight_region_match": 20,
            "weight_tech_match":   30,
            "weight_deadline":     10,
        },
        "alert": {"deadline_days": 3},
    }


def run_pipeline(config: dict) -> dict:
    """채용 공고 전체 처리 파이프라인"""
    raw_jobs = collect_all_jobs(config)
    if not raw_jobs:
        return {
            "jobs": [], "recommended": [], "deadline_soon": [],
            "tech_stats": [], "chart_data": {}, "total": 0,
        }

    jobs          = parse_and_clean(raw_jobs)
    jobs          = filter_expired(jobs)
    jobs          = score_jobs(jobs, config)
    deadline_soon = filter_deadline_soon(jobs, days=3)
    recommended   = get_recommended(jobs, top_n=10)
    recommended   = add_ai_content(recommended)
    tech_stats    = get_tech_stats(jobs)[:15]

    # ── 대시보드용 차트 데이터 계산 (기능 5) ──
    chart_data = _build_chart_data(jobs, tech_stats)

    return {
        "jobs":          jobs,
        "recommended":   recommended,
        "deadline_soon": deadline_soon,
        "tech_stats":    tech_stats,
        "chart_data":    chart_data,
        "total":         len(jobs),
    }


def _build_chart_data(jobs: list[dict], tech_stats: list[tuple]) -> dict:
    """Chart.js에 전달할 데이터 생성"""
    # 기술 키워드 TOP 15
    tech_labels  = [t[0] for t in tech_stats]
    tech_values  = [t[1] for t in tech_stats]

    # 고용형태 분포
    jt_counter   = Counter(j.get("job_type", "기타") or "기타" for j in jobs)
    jt_labels    = list(jt_counter.keys())
    jt_values    = list(jt_counter.values())

    # 적합도 점수 분포 (구간별)
    bins         = ["0-20", "21-40", "41-60", "61-80", "81-100"]
    bin_counts   = [0] * 5
    for j in jobs:
        s = j.get("score", 0)
        idx = min(int(s // 20), 4)
        bin_counts[idx] += 1

    # 출처별 공고 수
    src_counter  = Counter(j.get("source", "기타") for j in jobs)

    return {
        "tech":   {"labels": tech_labels,  "values": tech_values},
        "jtype":  {"labels": jt_labels,    "values": jt_values},
        "score":  {"labels": bins,         "values": bin_counts},
        "source": {"labels": list(src_counter.keys()),
                   "values": list(src_counter.values())},
    }


def make_template_ctx(result=None, form=None) -> dict:
    return {
        "region_options":     REGION_OPTIONS,
        "job_type_options":   JOB_TYPE_OPTIONS,
        "experience_options": EXPERIENCE_OPTIONS,
        "default_tech":       DEFAULT_TECH,
        "result":             result,
        "search_params":      form or {},
    }


# ============================================================
# 메인 페이지 라우트
# ============================================================
@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", **make_template_ctx())


@app.route("/search", methods=["POST"])
def search():
    try:
        config = build_config(request.form)
        result = run_pipeline(config)
    except Exception as e:
        flash(f"검색 중 오류가 발생했습니다: {e}", "error")
        return render_template("index.html", **make_template_ctx()), 500
    return render_template("index.html", **make_template_ctx(result, request.form))


# ============================================================
# 지원 현황 트래커 라우트 (기능 3)
# ============================================================
@app.route("/tracker")
def tracker():
    from datetime import datetime
    stats   = get_tracker_stats()
    grouped = get_applications_by_status()
    return render_template(
        "tracker.html",
        statuses=STATUSES,
        status_color=STATUS_COLOR,
        grouped=grouped,
        stats=stats,
        now=datetime.now(),
    )


@app.route("/tracker/add", methods=["POST"])
def tracker_add():
    company  = request.form.get("company", "").strip()
    title    = request.form.get("title", "").strip()
    if not company or not title:
        flash("회사명과 공고명은 필수입니다.", "error")
        return redirect(url_for("tracker"))

    add_application(
        company=company,
        title=title,
        link=request.form.get("link", ""),
        status=request.form.get("status", "지원완료"),
        deadline=request.form.get("deadline", ""),
        location=request.form.get("location", ""),
        score=float(request.form.get("score", 0) or 0),
        notes=request.form.get("notes", ""),
    )
    flash(f"'{company} - {title}' 지원 기록이 추가되었습니다.", "success")
    return redirect(url_for("tracker"))


@app.route("/tracker/update/<int:app_id>", methods=["POST"])
def tracker_update(app_id: int):
    status = request.form.get("status")
    notes  = request.form.get("notes")
    update_application(app_id, status=status, notes=notes)
    return redirect(url_for("tracker"))


@app.route("/tracker/delete/<int:app_id>", methods=["POST"])
def tracker_delete(app_id: int):
    delete_application(app_id)
    flash("지원 기록이 삭제되었습니다.", "success")
    return redirect(url_for("tracker"))


# ============================================================
# 공고 카드에서 바로 지원 기록 추가 (AJAX)
# ============================================================
@app.route("/tracker/quick-add", methods=["POST"])
def tracker_quick_add():
    """검색 결과 카드의 '지원 기록' 버튼에서 호출"""
    data    = request.get_json(silent=True) or {}
    company = data.get("company", "").strip()
    title   = data.get("title", "").strip()
    if not company or not title:
        return jsonify({"ok": False, "msg": "회사명/공고명 누락"}), 400

    new_id = add_application(
        company=company,
        title=title,
        link=data.get("link", ""),
        status="지원완료",
        deadline=data.get("deadline", ""),
        location=data.get("location", ""),
        score=float(data.get("score", 0) or 0),
    )
    return jsonify({"ok": True, "id": new_id})


# ============================================================
# 실행
# ============================================================
if __name__ == "__main__":
    import os
    from waitress import serve
    init_tracker_db()
    port = int(os.environ.get("PORT", 5000))
    serve(app, host="0.0.0.0", port=port)
