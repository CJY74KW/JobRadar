"""
data_parser.py
수집된 채용 공고 데이터 파싱 및 정제 모듈
- 필수 항목 추출, 날짜 정규화, 중복 제거, D-day 계산
"""

import re
from datetime import datetime, date


def parse_and_clean(raw_jobs: list[dict]) -> list[dict]:
    """수집 데이터 전처리 파이프라인"""
    jobs = [_normalize_fields(job) for job in raw_jobs]
    jobs = _remove_duplicates(jobs)
    jobs = [_calc_dday(job) for job in jobs]
    jobs = [_extract_tech_keywords(job) for job in jobs]
    return jobs


def _normalize_fields(job: dict) -> dict:
    """날짜 형식 통일 및 빈 문자열 처리"""
    cleaned = {}
    for k, v in job.items():
        cleaned[k] = v.strip() if isinstance(v, str) else (v or "")

    # 날짜 정규화: YYYYMMDD → YYYY-MM-DD
    dl = cleaned.get("deadline", "")
    if dl and len(dl) == 8 and dl.isdigit():
        cleaned["deadline"] = f"{dl[:4]}-{dl[4:6]}-{dl[6:]}"

    pd_ = cleaned.get("posted_date", "")
    if pd_ and len(pd_) == 8 and pd_.isdigit():
        cleaned["posted_date"] = f"{pd_[:4]}-{pd_[4:6]}-{pd_[6:]}"

    # 마감일 없으면 '상시채용'으로 표시
    if not cleaned.get("deadline"):
        cleaned["deadline"] = "상시채용"

    return cleaned


def _remove_duplicates(jobs: list[dict]) -> list[dict]:
    """회사명 + 공고제목 + 마감일 기준 중복 제거"""
    seen = set()
    unique = []
    for job in jobs:
        key = (
            _normalize_str(job.get("company", "")),
            _normalize_str(job.get("title", "")),
            job.get("deadline", ""),
        )
        if key not in seen:
            seen.add(key)
            unique.append(job)
    removed = len(jobs) - len(unique)
    if removed:
        print(f"[정제] 중복 공고 {removed}개 제거 → 총 {len(unique)}개")
    return unique


def _normalize_str(s: str) -> str:
    """비교를 위한 문자열 정규화 (공백·특수문자 제거, 소문자화)"""
    return re.sub(r"[\s\W]+", "", s).lower()


def _calc_dday(job: dict) -> dict:
    """마감일 기준 D-day 계산"""
    deadline = job.get("deadline", "")
    if deadline == "상시채용":
        job["dday"] = "상시"
        job["dday_num"] = 9999
        return job

    try:
        dl_date = datetime.strptime(deadline, "%Y-%m-%d").date()
        today = date.today()
        diff = (dl_date - today).days
        if diff < 0:
            job["dday"] = "마감"
            job["dday_num"] = -1
        elif diff == 0:
            job["dday"] = "D-Day"
            job["dday_num"] = 0
        else:
            job["dday"] = f"D-{diff}"
            job["dday_num"] = diff
    except ValueError:
        job["dday"] = "확인필요"
        job["dday_num"] = 9998

    return job


# 추출 대상 기술 키워드 사전
TECH_KEYWORDS = [
    "Python", "Java", "JavaScript", "TypeScript", "C++", "C#", "Go", "Kotlin",
    "Swift", "R", "Scala", "Ruby", "PHP",
    "Django", "Flask", "FastAPI", "Spring", "React", "Vue", "Angular", "Node.js",
    "AWS", "GCP", "Azure", "Docker", "Kubernetes", "Terraform", "Linux",
    "SQL", "MySQL", "PostgreSQL", "MongoDB", "Redis", "Elasticsearch",
    "Pandas", "NumPy", "Scikit-learn", "TensorFlow", "PyTorch", "Spark",
    "Git", "CI/CD", "REST", "GraphQL", "Kafka", "RabbitMQ",
    "Tableau", "Power BI", "Hadoop",
]


def _extract_tech_keywords(job: dict) -> dict:
    """공고 본문에서 기술 키워드 추출"""
    text = " ".join([
        job.get("description", ""),
        job.get("requirements", ""),
        job.get("preferred", ""),
        job.get("title", ""),
    ]).lower()

    found = [kw for kw in TECH_KEYWORDS if kw.lower() in text]
    job["tech_keywords"] = list(dict.fromkeys(found))  # 순서 유지 + 중복 제거
    return job


def filter_expired(jobs: list[dict]) -> list[dict]:
    """마감된 공고 제거"""
    return [j for j in jobs if j.get("dday_num", -1) != -1]


def filter_deadline_soon(jobs: list[dict], days: int = 3) -> list[dict]:
    """마감 임박 공고 추출 (D-day 기준)"""
    return [j for j in jobs if 0 <= j.get("dday_num", 9999) <= days]
