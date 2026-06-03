"""
app.py
채용 정보 웹 애플리케이션 - Flask 백엔드
모든 데이터 수집·분석·렌더링 로직은 Python에서 처리
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from flask import Flask, render_template, request

from api_collector import collect_all_jobs
from data_parser import parse_and_clean, filter_expired, filter_deadline_soon
from analyzer import score_jobs, get_recommended, get_tech_stats
from ai_generator import add_ai_content

app = Flask(__name__)

# ============================================================
# 공통 상수
# ============================================================
REGION_OPTIONS = [
    "서울", "경기", "인천", "부산", "대구", "대전",
    "광주", "울산", "강원", "충북", "충남", "전북",
    "전남", "경북", "경남", "제주", "세종",
]
JOB_TYPE_OPTIONS = ["정규직", "계약직", "인턴", "아르바이트"]
EXPERIENCE_OPTIONS = ["신입", "경력"]
DEFAULT_TECH = "Python, SQL, React, AWS, Django"


# ============================================================
# 헬퍼 함수 (비즈니스 로직 - 전부 Python에서 처리)
# ============================================================
def build_config(form) -> dict:
    """폼 데이터 → 분석 설정 딕셔너리 변환"""
    tech_raw = form.get("tech_stack", DEFAULT_TECH)
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
    """
    채용 공고 전체 처리 파이프라인
    1. 수집 → 2. 파싱·정제 → 3. 점수화 → 4. 분류 → 5. AI 콘텐츠 → 6. 통계
    """
    # 1. 수집
    raw_jobs = collect_all_jobs(config)
    if not raw_jobs:
        return {
            "jobs": [], "recommended": [],
            "deadline_soon": [], "tech_stats": [], "total": 0,
        }

    # 2. 파싱 및 정제 (날짜 정규화, 중복 제거, D-day 계산, 기술키워드 추출)
    jobs = parse_and_clean(raw_jobs)
    jobs = filter_expired(jobs)

    # 3. 적합도 점수화 (직무·지역·기술스택·마감일 가중치 적용)
    jobs = score_jobs(jobs, config)

    # 4. 분류
    deadline_soon = filter_deadline_soon(jobs, days=3)
    recommended   = get_recommended(jobs, top_n=10)

    # 5. AI 콘텐츠 생성 (자소서 포인트 + 면접 질문) — 추천 공고 기준
    recommended = add_ai_content(recommended)

    # 6. 기술 키워드 빈도 통계
    tech_stats = get_tech_stats(jobs)[:15]

    return {
        "jobs":          jobs,
        "recommended":   recommended,
        "deadline_soon": deadline_soon,
        "tech_stats":    tech_stats,
        "total":         len(jobs),
    }


def make_template_ctx(result=None, form=None) -> dict:
    """템플릿 공통 컨텍스트 생성"""
    return {
        "region_options":     REGION_OPTIONS,
        "job_type_options":   JOB_TYPE_OPTIONS,
        "experience_options": EXPERIENCE_OPTIONS,
        "default_tech":       DEFAULT_TECH,
        "result":             result,
        "search_params":      form or {},
    }


# ============================================================
# 라우트
# ============================================================
@app.route("/", methods=["GET"])
def index():
    """메인 페이지 - 검색 폼만 렌더링"""
    return render_template("index.html", **make_template_ctx())


@app.route("/search", methods=["POST"])
def search():
    """검색 처리 - Python이 모든 분석 수행 후 결과 렌더링"""
    config = build_config(request.form)
    result = run_pipeline(config)
    return render_template("index.html", **make_template_ctx(result, request.form))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
