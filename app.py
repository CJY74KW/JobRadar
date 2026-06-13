"""
app.py
채용 정보 웹 애플리케이션 - Flask 백엔드
"""

import sys
import io
import logging
import os
import uuid
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s:%(name)s:%(message)s",
    stream=sys.stderr,
)

from collections import Counter

from flask import Flask, render_template, request, jsonify, flash, send_file, abort

from api_collector import collect_all_jobs
from data_parser   import parse_and_clean, filter_expired, filter_deadline_soon
from analyzer      import score_jobs, filter_by_user_tech, get_recommended, get_tech_stats
from ai_generator  import _ai_generate_claude, generate_cover_letter_points, generate_interview_questions
from pdf_report    import save_search_pdf_report, save_job_ai_pdf_report
from storage       import save_all_jobs_excel

app = Flask(__name__)
app.secret_key = "job-search-secret-key-2026"

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
ALL_JOBS_EXCEL_PATH = "output/채용공고_전체.xlsx"
ALL_JOBS_PDF_PATH = "output/채용공고_보고서.pdf"
REPORTS_DIR = "output/reports"


# ============================================================
# 헬퍼 함수
# ============================================================
def build_config(form) -> dict:
    tech_raw   = form.get("tech_stack", DEFAULT_TECH)
    tech_stack = [t.strip() for t in tech_raw.split(",") if t.strip()]
    return {
        "search": {
            "region":     form.get("region", ""),
            "job_type":   form.get("job_type", ""),
            "experience": form.get("experience", ""),
            "tech_stack": tech_stack,
        },
        "scoring": {
            "tech":       45,
            "experience": 10,
            "job_type":   7,
            "region":     8,
            "deadline":   3,
            "quality":    2,
        },
        "alert": {"deadline_days": 3},
        "output": {
            "all_excel_path": ALL_JOBS_EXCEL_PATH,
            "all_pdf_path":   ALL_JOBS_PDF_PATH,
        },
    }


def run_pipeline(config: dict) -> dict:
    """채용 공고 전체 처리 파이프라인"""
    excel_path = config["output"]["all_excel_path"]
    pdf_path = config["output"]["all_pdf_path"]
    raw_jobs = collect_all_jobs(config)
    if not raw_jobs:
        chart_data = _build_chart_data([], [])
        save_all_jobs_excel([], excel_path)
        save_search_pdf_report([], [], chart_data, pdf_path, config.get("search", {}))
        return {
            "jobs": [], "recommended": [], "deadline_soon": [],
            "tech_stats": [], "chart_data": chart_data, "total": 0,
            "excel_path": excel_path,
            "excel_download_url": "/download/all-jobs",
            "pdf_path": pdf_path,
            "pdf_download_url": "/download/all-jobs-pdf",
        }

    jobs          = parse_and_clean(raw_jobs)
    jobs          = filter_expired(jobs)
    jobs          = filter_by_user_tech(jobs, config)
    jobs          = score_jobs(jobs, config)
    deadline_soon = filter_deadline_soon(jobs, days=3)
    recommended   = get_recommended(jobs, top_n=10)
    tech_stats    = get_tech_stats(jobs)[:15]
    save_all_jobs_excel(jobs, excel_path, tech_stats)

    # ── 대시보드용 차트 데이터 계산 (기능 5) ──
    chart_data = _build_chart_data(jobs, tech_stats)
    save_search_pdf_report(jobs, tech_stats, chart_data, pdf_path, config.get("search", {}))

    return {
        "jobs":          jobs,
        "recommended":   recommended,
        "deadline_soon": deadline_soon,
        "tech_stats":    tech_stats,
        "chart_data":    chart_data,
        "total":         len(jobs),
        "excel_path":    excel_path,
        "excel_download_url": "/download/all-jobs",
        "pdf_path":      pdf_path,
        "pdf_download_url": "/download/all-jobs-pdf",
    }


def _build_chart_data(jobs: list[dict], tech_stats: list[tuple]) -> dict:
    """Chart.js에 전달할 데이터 생성"""
    # 기술 키워드 TOP 15
    tech_labels  = [t[0] for t in tech_stats]
    tech_values  = [t[1] for t in tech_stats]

    # 적합도 점수 분포 (구간별)
    bins         = ["0-20", "21-40", "41-60", "61-80", "81-100"]
    bin_counts   = [0] * 5
    for j in jobs:
        try:
            s = float(j.get("score", 0) or 0)
        except (TypeError, ValueError):
            s = 0
        if s <= 20:
            idx = 0
        elif s <= 40:
            idx = 1
        elif s <= 60:
            idx = 2
        elif s <= 80:
            idx = 3
        else:
            idx = 4
        bin_counts[idx] += 1

    # 출처별 공고 수
    src_counter  = Counter(j.get("source", "기타") for j in jobs)

    return {
        "tech":   {"labels": tech_labels,  "values": tech_values},
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
# AI 콘텐츠 온디맨드 API
# ============================================================
@app.route("/api/ai-content", methods=["POST"])
def api_ai_content():
    """공고 카드에서 버튼 클릭 시 자소서 포인트·면접 질문을 즉시 생성"""
    try:
        job = request.get_json(force=True, silent=True) or {}
        if not job:
            return jsonify({"error": "job data required"}), 400

        cl_points, cl_questions = _ai_generate_claude(job)
        if not cl_points:
            cl_points    = generate_cover_letter_points(job)
            cl_questions = generate_interview_questions(job)

        report_url = ""
        try:
            os.makedirs(REPORTS_DIR, exist_ok=True)
            report_name = f"job_report_{uuid.uuid4().hex}.pdf"
            report_path = os.path.join(REPORTS_DIR, report_name)
            save_job_ai_pdf_report(job, cl_points, cl_questions, report_path)
            report_url = f"/download/reports/{report_name}"
        except Exception as report_error:
            app.logger.error(f"[ai-content-report] PDF 생성 오류: {report_error}")

        return jsonify({
            "cover_letter_points": cl_points,
            "interview_questions": cl_questions,
            "report_download_url": report_url,
        })
    except Exception as e:
        app.logger.error(f"[ai-content] 오류: {e}")
        return jsonify({"error": str(e)}), 500


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


@app.route("/download/all-jobs", methods=["GET"])
def download_all_jobs_excel():
    path = os.path.abspath(ALL_JOBS_EXCEL_PATH)
    if not os.path.exists(path):
        abort(404)
    return send_file(
        path,
        as_attachment=True,
        download_name=os.path.basename(path),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/download/all-jobs-pdf", methods=["GET"])
def download_all_jobs_pdf():
    path = os.path.abspath(ALL_JOBS_PDF_PATH)
    if not os.path.exists(path):
        abort(404)
    return send_file(
        path,
        as_attachment=True,
        download_name=os.path.basename(path),
        mimetype="application/pdf",
    )


@app.route("/download/reports/<filename>", methods=["GET"])
def download_job_pdf_report(filename: str):
    safe_name = os.path.basename(filename)
    if safe_name != filename or not safe_name.lower().endswith(".pdf"):
        abort(404)

    base_dir = os.path.abspath(REPORTS_DIR)
    path = os.path.abspath(os.path.join(base_dir, safe_name))
    if os.path.commonpath([base_dir, path]) != base_dir or not os.path.exists(path):
        abort(404)

    return send_file(
        path,
        as_attachment=True,
        download_name=safe_name,
        mimetype="application/pdf",
    )


# ============================================================
# 실행
# ============================================================
if __name__ == "__main__":
    import os
    from waitress import serve
    port = int(os.environ.get("PORT", 5000))
    serve(app, host="0.0.0.0", port=port)
