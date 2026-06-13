"""
analyzer.py
공고 필터링 및 적합도 점수화 모듈
- 직무 일치도, 지역 일치도, 기술 스택 일치도, 마감일 점수 계산
- 우선순위 정렬 및 추천 공고 선별
"""

import re
from collections import Counter


DEFAULT_SCORE_WEIGHTS = {
    "tech": 45,
    "role": 25,
    "experience": 10,
    "job_type": 7,
    "region": 8,
    "deadline": 3,
    "quality": 2,
}


def score_jobs(jobs: list[dict], config: dict) -> list[dict]:
    """공고별 객관 지표 기반 100점 적합도 점수를 부여하고 내림차순 정렬"""
    search = config.get("search", {})
    criteria = {
        "keyword": "",
        "region": search.get("region", "").strip(),
        "experience": search.get("experience", "").strip(),
        "job_type": search.get("job_type", "").strip(),
        "tech_stack": [
            t.strip()
            for t in search.get("tech_stack", [])
            if isinstance(t, str) and t.strip()
        ],
    }
    weights = _build_score_weights(config.get("scoring", {}))

    for job in jobs:
        score, breakdown = _calc_score(job, criteria, weights)
        job["score"] = score
        job["score_breakdown"] = breakdown
        job["match_detail"] = _build_match_detail(breakdown)

    return sorted(jobs, key=lambda j: j["score"], reverse=True)


def filter_by_user_tech(jobs: list[dict], config: dict) -> list[dict]:
    """사용자가 입력한 기술 스택을 하나라도 포함한 공고만 남긴다."""
    user_tech = [
        t.strip()
        for t in config["search"].get("tech_stack", [])
        if isinstance(t, str) and t.strip()
    ]
    if not user_tech:
        return jobs

    matched_jobs = []
    for job in jobs:
        matched = _get_user_tech_matches(job, user_tech)
        if matched:
            _merge_user_tech_matches(job, matched)
            matched_jobs.append(job)

    return matched_jobs


def _build_score_weights(config_weights: dict) -> dict:
    weights = DEFAULT_SCORE_WEIGHTS.copy()
    for key in weights:
        try:
            if key in config_weights:
                weights[key] = float(config_weights[key])
        except (TypeError, ValueError):
            pass
    return weights


def _calc_score(job: dict, criteria: dict, weights: dict) -> tuple[float, dict]:
    breakdown = {}
    breakdown["tech"] = _score_tech(job, criteria["tech_stack"], weights["tech"])
    breakdown["role"] = _score_role(job, criteria["keyword"], weights["role"])
    breakdown["experience"] = _score_experience(
        job, criteria["experience"], weights["experience"]
    )
    breakdown["job_type"] = _score_job_type(job, criteria["job_type"], weights["job_type"])
    breakdown["region"] = _score_region(job, criteria["region"], weights["region"])
    breakdown["deadline"] = _score_deadline(job, weights["deadline"])
    breakdown["quality"] = _score_quality(job, weights["quality"])

    active_parts = [part for part in breakdown.values() if part.get("active", True)]
    total = sum(part["score"] for part in active_parts)
    total -= sum(part.get("penalty", 0) for part in active_parts)
    max_total = sum(part["max"] for part in active_parts)
    if max_total and max_total != 100:
        total = total / max_total * 100

    return round(min(max(total, 0), 100), 2), breakdown


def _score_tech(job: dict, user_tech: list[str], max_score: float) -> dict:
    if not user_tech:
        return _inactive_part("기술스택 조건 없음")

    matched = _unique_preserve_order(_get_user_tech_matches(job, user_tech))
    _merge_user_tech_matches(job, matched)
    job_tech = _get_job_tech_keywords(job)
    match_count = len(matched)
    required_count = len(job_tech)

    if not required_count:
        return _score_part(0, max_score, "공고 기술 정보 없음")

    ratio = min(match_count / required_count, 1.0)
    if ratio >= 1.0:
        label = f"공고기술 {match_count}/{required_count}개 모두 커버"
        if matched:
            label += f": {', '.join(matched[:5])}"
            if len(matched) > 5:
                label += f" 외 {len(matched) - 5}개"
        return _score_part(max_score, max_score, label)

    ratio_score = max_score * 0.80 * (ratio ** 1.25)
    placement_score = _score_tech_placement(job, matched, max_score * 0.15)
    breadth_score = _score_tech_breadth(match_count, ratio, max_score * 0.05)
    score = min(ratio_score + placement_score + breadth_score, max_score)

    missing = _missing_job_tech(job_tech, matched)
    label = f"공고기술 {match_count}/{required_count}개 커버"
    if matched:
        label += f": {', '.join(matched[:5])}"
        if len(matched) > 5:
            label += f" 외 {len(matched) - 5}개"
    if missing:
        label += f" / 부족: {', '.join(missing[:3])}"
        if len(missing) > 3:
            label += f" 외 {len(missing) - 3}개"
    return _score_part(score, max_score, label)


def _score_tech_placement(job: dict, matched: list[str], max_score: float) -> float:
    if not matched:
        return 0.0

    title = str(job.get("title", ""))
    requirements = str(job.get("requirements", ""))
    preferred = str(job.get("preferred", ""))
    description = str(job.get("description", ""))

    title_score = 0.0
    requirements_score = 0.0
    body_score = 0.0
    for tech in matched:
        if _contains_tech(title, tech):
            title_score += 1
        if _contains_tech(requirements, tech):
            requirements_score += 1
        if _contains_tech(preferred, tech) or _contains_tech(description, tech):
            body_score += 1

    title_score = min(title_score, 2) / 2 * (max_score * 0.40)
    requirements_score = min(requirements_score, 2) / 2 * (max_score * 0.40)
    body_score = min(body_score, 2) / 2 * (max_score * 0.20)
    return title_score + requirements_score + body_score


def _score_tech_breadth(match_count: int, ratio: float, max_score: float) -> float:
    if match_count >= 4 or ratio >= 0.75:
        return max_score
    if match_count >= 3 or ratio >= 0.50:
        return max_score * 0.70
    if match_count >= 2:
        return max_score * 0.40
    if match_count == 1:
        return max_score * 0.15
    return 0.0


def _score_role(job: dict, keyword: str, max_score: float) -> dict:
    keyword = keyword.strip()
    if not keyword:
        return _inactive_part("검색 키워드 조건 없음")

    title = str(job.get("title", ""))
    body = " ".join(
        str(job.get(field, ""))
        for field in ("description", "requirements", "preferred")
    )
    keyword_lower = keyword.lower()
    title_lower = title.lower()
    body_lower = body.lower()
    tokens = _keyword_tokens(keyword)

    score = 0.0
    signals = []
    if keyword_lower in title_lower:
        score += max_score * 0.50
        signals.append("제목 직접")
    elif tokens:
        title_ratio = _token_ratio(tokens, title_lower)
        if title_ratio:
            score += max_score * 0.40 * title_ratio
            signals.append(f"제목 토큰 {title_ratio:.0%}")

    if keyword_lower in body_lower:
        score += max_score * 0.30
        signals.append("본문 직접")
    elif tokens:
        body_ratio = _token_ratio(tokens, body_lower)
        if body_ratio:
            score += max_score * 0.25 * body_ratio
            signals.append(f"본문 토큰 {body_ratio:.0%}")

    if tokens:
        all_text_ratio = _token_ratio(tokens, f"{title_lower} {body_lower}")
        score += max_score * 0.20 * all_text_ratio

    label = ", ".join(signals) if signals else "키워드 근거 약함"
    return _score_part(min(score, max_score), max_score, label)


def _score_experience(job: dict, target: str, max_score: float) -> dict:
    target = target.strip()
    if not target:
        return _inactive_part("경력 조건 없음")

    text = _normalize_text(job.get("experience", ""))
    if not text:
        return _score_part(max_score * 0.20, max_score, "경력 정보 없음")

    is_open = any(word in text for word in ("무관", "경력무관", "신입/경력", "신입경력"))
    if target == "신입":
        if "신입" in text:
            return _score_part(max_score, max_score, "신입 명시")
        if is_open:
            return _score_part(max_score * 0.85, max_score, "신입 지원 가능")
        if "경력" in text or re.search(r"\d+\s*년", text):
            return _score_part(0, max_score, "경력직 중심", penalty=max_score * 0.50)
        return _score_part(max_score * 0.20, max_score, "판단 정보 부족")

    if target == "경력":
        if "경력" in text or re.search(r"\d+\s*년", text):
            return _score_part(max_score, max_score, "경력 명시")
        if is_open:
            return _score_part(max_score * 0.75, max_score, "경력 지원 가능")
        if "신입" in text:
            return _score_part(0, max_score, "신입 중심", penalty=max_score * 0.50)
        return _score_part(max_score * 0.20, max_score, "판단 정보 부족")

    if _normalize_text(target) in text:
        return _score_part(max_score, max_score, "조건 일치")
    return _score_part(max_score * 0.20, max_score, "판단 정보 부족")


def _score_job_type(job: dict, target: str, max_score: float) -> dict:
    target = target.strip()
    if not target:
        return _inactive_part("고용형태 조건 없음")

    text = _normalize_text(job.get("job_type", ""))
    if not text:
        return _score_part(max_score * 0.20, max_score, "고용형태 정보 없음")
    if _normalize_text(target) in text:
        return _score_part(max_score, max_score, "고용형태 일치")
    return _score_part(0, max_score, "고용형태 불일치", penalty=max_score * 0.40)


def _score_region(job: dict, target: str, max_score: float) -> dict:
    target = target.strip()
    if not target:
        return _inactive_part("지역 조건 없음")

    location = str(job.get("location", "")).strip()
    if not location:
        return _score_part(max_score * 0.20, max_score, "지역 정보 없음")
    if target in location:
        return _score_part(max_score, max_score, "지역 직접 일치")
    if _region_province_match(target, location):
        return _score_part(max_score * 0.70, max_score, "권역 일치")
    if _is_remote_or_nationwide(location):
        return _score_part(max_score * 0.60, max_score, "원격/전국 가능")
    return _score_part(0, max_score, "선택 지역과 다름", penalty=max_score * 0.35)


def _score_deadline(job: dict, max_score: float) -> dict:
    dday = job.get("dday_num", 9999)
    if dday == 9999:
        return _score_part(max_score * 0.60, max_score, "상시채용")
    if dday == 9998:
        return _score_part(max_score * 0.40, max_score, "마감 확인 필요")
    if dday >= 30:
        return _score_part(max_score * 0.80, max_score, "30일 이상 여유")
    if 7 <= dday < 30:
        return _score_part(max_score, max_score, "7~29일 여유")
    if 3 <= dday < 7:
        return _score_part(max_score * 0.70, max_score, "3~6일 남음")
    if 1 <= dday < 3:
        return _score_part(max_score * 0.35, max_score, "1~2일 남음")
    if dday == 0:
        return _score_part(max_score * 0.20, max_score, "오늘 마감")
    return _score_part(0, max_score, "마감")


def _score_quality(job: dict, max_score: float) -> dict:
    checks = {
        "회사": bool(job.get("company")),
        "제목": bool(job.get("title")),
        "링크": bool(job.get("link")),
        "지역": bool(job.get("location")),
        "본문": any(job.get(field) for field in ("description", "requirements", "preferred")),
    }
    passed = [name for name, ok in checks.items() if ok]
    score = max_score * len(passed) / len(checks)
    return _score_part(score, max_score, f"{len(passed)}/{len(checks)}개 정보")


def _get_user_tech_matches(job: dict, user_tech: list[str]) -> list[str]:
    raw_keywords = job.get("tech_keywords", []) or []
    if isinstance(raw_keywords, str):
        raw_keywords = [kw.strip() for kw in raw_keywords.split(",") if kw.strip()]

    keyword_lookup = {_normalize_tech(kw) for kw in raw_keywords}
    search_text = " ".join(
        str(job.get(field, ""))
        for field in ("title", "description", "requirements", "preferred")
    ).lower()
    compact_text = _compact_for_match(search_text)

    matches = []
    for tech in user_tech:
        norm = _normalize_tech(tech)
        compact = _compact_for_match(tech)
        if not norm:
            continue
        if norm in keyword_lookup or norm in search_text or (compact and compact in compact_text):
            matches.append(tech)
    return matches


def _get_job_tech_keywords(job: dict) -> list[str]:
    raw_keywords = job.get("tech_keywords", []) or []
    if isinstance(raw_keywords, str):
        raw_keywords = [kw.strip() for kw in raw_keywords.split(",") if kw.strip()]
    return _unique_preserve_order([kw for kw in raw_keywords if str(kw).strip()])


def _missing_job_tech(job_tech: list[str], matched: list[str]) -> list[str]:
    matched_lookup = {_normalize_tech(tech) for tech in matched}
    return [
        tech for tech in job_tech
        if _normalize_tech(tech) not in matched_lookup
    ]


def _merge_user_tech_matches(job: dict, matched: list[str]) -> None:
    raw_keywords = job.get("tech_keywords", []) or []
    if isinstance(raw_keywords, str):
        raw_keywords = [kw.strip() for kw in raw_keywords.split(",") if kw.strip()]

    existing = list(raw_keywords)
    existing_lookup = {_normalize_tech(kw) for kw in existing}
    for tech in matched:
        norm = _normalize_tech(tech)
        if norm and norm not in existing_lookup:
            existing.append(tech)
            existing_lookup.add(norm)

    job["tech_keywords"] = existing
    job["user_tech_matches"] = matched


def _normalize_tech(value: str) -> str:
    return str(value).strip().lower()


def _compact_for_match(value: str) -> str:
    return re.sub(r"[\s._/\-]+", "", str(value).lower())


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value).lower())


def _contains_tech(text: str, tech: str) -> bool:
    text_lower = str(text).lower()
    tech_lower = _normalize_tech(tech)
    tech_compact = _compact_for_match(tech)
    return (
        bool(tech_lower and tech_lower in text_lower) or
        bool(tech_compact and tech_compact in _compact_for_match(text_lower))
    )


def _keyword_tokens(keyword: str) -> list[str]:
    tokens = re.split(r"[\s,;/|]+", keyword.lower())
    return [t for t in tokens if t]


def _token_ratio(tokens: list[str], text: str) -> float:
    if not tokens:
        return 0.0
    matched = sum(1 for token in tokens if token in text)
    return matched / len(tokens)


def _unique_preserve_order(values: list[str]) -> list[str]:
    seen = set()
    unique = []
    for value in values:
        key = _normalize_tech(value)
        if key and key not in seen:
            seen.add(key)
            unique.append(value)
    return unique


def _score_part(score: float, max_score: float, label: str,
                active: bool = True, penalty: float = 0.0) -> dict:
    return {
        "score": round(score, 2),
        "max": round(max_score, 2),
        "label": label,
        "active": active,
        "penalty": round(penalty, 2),
    }


def _inactive_part(label: str) -> dict:
    return _score_part(0, 0, label, active=False)


def _is_remote_or_nationwide(location: str) -> bool:
    normalized = _normalize_text(location)
    return any(
        word in normalized
        for word in ("재택", "원격", "리모트", "remote", "전국", "근무지무관", "지역무관")
    )


def _region_province_match(user_region: str, job_region: str) -> bool:
    """광역시도 수준 부분 매칭"""
    provinces = {
        "서울": ["서울"],
        "경기": ["경기", "경기도", "수원", "성남", "고양", "용인", "부천", "안산", "안양", "남양주"],
        "인천": ["인천"],
        "부산": ["부산"],
        "대구": ["대구"],
        "대전": ["대전"],
        "광주": ["광주"],
        "울산": ["울산"],
        "강원": ["강원", "강원도", "춘천", "원주", "강릉"],
        "충북": ["충북", "충청북도", "청주", "충주", "제천"],
        "충남": ["충남", "충청남도", "천안", "아산", "공주", "서산"],
        "전북": ["전북", "전라북도", "전주", "군산", "익산"],
        "전남": ["전남", "전라남도", "목포", "여수", "순천"],
        "경북": ["경북", "경상북도", "포항", "구미", "경주"],
        "경남": ["경남", "경상남도", "창원", "김해", "진주", "양산"],
        "제주": ["제주", "제주도", "제주특별자치도"],
        "세종": ["세종"],
    }
    targets = provinces.get(user_region, [user_region])
    return any(t in job_region for t in targets)


def _build_match_detail(breakdown: dict) -> str:
    """카드와 엑셀에 표시할 항목별 점수 근거 문자열 생성"""
    names = {
        "tech": "기술",
        "role": "직무",
        "experience": "경력",
        "job_type": "고용",
        "region": "지역",
        "deadline": "마감",
        "quality": "정보",
    }
    parts = []
    for key in ("tech", "role", "experience", "job_type", "region", "deadline", "quality"):
        item = breakdown[key]
        if not item.get("active", True):
            continue
        score = _format_score(item["score"])
        max_score = _format_score(item["max"])
        label = item["label"]
        if item.get("penalty", 0):
            label = f"{label}, 감점 {_format_score(item['penalty'])}"
        parts.append(f"{names[key]} {score}/{max_score}({label})")
    return " | ".join(parts)


def _format_score(value: float) -> str:
    value = round(float(value), 1)
    return str(int(value)) if value.is_integer() else f"{value:.1f}"


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
