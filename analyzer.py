"""
analyzer.py
공고 필터링 및 적합도 점수화 모듈
- 직무 일치도, 지역 일치도, 기술 스택 일치도, 마감일 점수 계산
- 우선순위 정렬 및 추천 공고 선별
"""

import re
from collections import Counter


def score_jobs(jobs: list[dict], config: dict) -> list[dict]:
    """모든 공고에 적합도 점수를 부여하고 내림차순 정렬"""
    weights = config.get("scoring", {
        "weight_job_match": 40,
        "weight_region_match": 20,
        "weight_tech_match": 30,
        "weight_deadline": 10,
    })
    user_tech = [t.lower() for t in config["search"].get("tech_stack", [])]
    user_region = config["search"].get("region", "").strip()
    user_keyword = config["search"].get("keyword", "").strip().lower()

    for job in jobs:
        job["score"] = _calc_score(job, user_keyword, user_region, user_tech, weights)
        job["match_detail"] = _build_match_detail(job, user_keyword, user_region, user_tech)

    return sorted(jobs, key=lambda j: j["score"], reverse=True)


def _calc_score(job: dict, keyword: str, region: str,
                user_tech: list, weights: dict) -> float:
    score = 0.0

    # 1. 직무 일치도 (40점)
    title_lower = job.get("title", "").lower()
    desc_lower = job.get("description", "").lower()
    if keyword and (keyword in title_lower or keyword in desc_lower):
        score += weights["weight_job_match"]
    elif keyword:
        # 부분 단어 일치 시 절반 점수
        parts = keyword.split()
        if any(p in title_lower or p in desc_lower for p in parts):
            score += weights["weight_job_match"] * 0.5

    # 2. 지역 일치도 (20점)
    job_region = job.get("location", "")
    if region and region in job_region:
        score += weights["weight_region_match"]
    elif region and _region_province_match(region, job_region):
        score += weights["weight_region_match"] * 0.5

    # 3. 기술 스택 일치도 (30점)
    job_tech = [t.lower() for t in job.get("tech_keywords", [])]
    if user_tech and job_tech:
        matched = len(set(user_tech) & set(job_tech))
        ratio = min(matched / len(user_tech), 1.0)
        score += weights["weight_tech_match"] * ratio

    # 4. 마감일 점수 (10점) — 적당히 여유 있는 공고 우대
    dday = job.get("dday_num", 9999)
    if dday == 9999:          # 상시채용
        score += weights["weight_deadline"] * 0.5
    elif 7 <= dday <= 30:     # 1주~1달 내 마감: 최고점
        score += weights["weight_deadline"]
    elif 3 <= dday < 7:       # 임박
        score += weights["weight_deadline"] * 0.8
    elif dday < 3:            # 매우 임박
        score += weights["weight_deadline"] * 0.3

    return round(score, 2)


def _region_province_match(user_region: str, job_region: str) -> bool:
    """광역시도 수준 부분 매칭"""
    provinces = {
        "서울": ["서울"],
        "경기": ["경기", "수원", "성남", "고양", "용인", "부천", "안산", "안양", "남양주"],
        "인천": ["인천"],
        "부산": ["부산"],
        "대구": ["대구"],
    }
    targets = provinces.get(user_region, [user_region])
    return any(t in job_region for t in targets)


def _build_match_detail(job: dict, keyword: str, region: str, user_tech: list) -> str:
    """매칭 세부 정보 문자열 생성"""
    details = []
    title_lower = job.get("title", "").lower()
    if keyword and keyword in title_lower:
        details.append(f"직무키워드 일치")
    job_tech = [t.lower() for t in job.get("tech_keywords", [])]
    matched_tech = [t for t in user_tech if t in job_tech]
    if matched_tech:
        details.append(f"기술매칭: {', '.join(matched_tech)}")
    if region and region in job.get("location", ""):
        details.append(f"지역 일치")
    return " | ".join(details) if details else "부분 매칭"


def get_recommended(jobs: list[dict], top_n: int = 10) -> list[dict]:
    """상위 N개 추천 공고 반환"""
    return [j for j in jobs if j.get("score", 0) > 0][:top_n]


def get_tech_stats(jobs: list[dict]) -> list[tuple]:
    """전체 공고에서 기술 키워드 빈도 집계"""
    counter = Counter()
    for job in jobs:
        for kw in job.get("tech_keywords", []):
            counter[kw] += 1
    return counter.most_common()
