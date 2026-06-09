"""
api_collector.py  ―  채용정보 수집 모듈 (v3 초안)

수집 우선순위:
  1. 원티드   ─ 비공식 JSON API   (설정 불필요, 기본 활성화)  ★ IT/스타트업 중심
  2. 잡코리아 ─ HTML 스크래핑     (설정 불필요, 기본 활성화)  ★ 전 직군 커버
  3. 워크넷   ─ 공공 API          (WORKNET_API_KEY 설정 시)   보조 소스
  4. 사람인   ─ 공식 API          (SARAMIN_API_KEY 설정 시)   보조 소스

[초안 주의사항]
  - 잡코리아 HTML 셀렉터는 사이트 구조 변경 시 수정이 필요합니다.
    파싱 실패 시 output/jobkorea_debug.html 파일에 원본 HTML이 저장됩니다.
  - 원티드 API 파라미터는 공식 문서가 없어 비공식으로 파악된 구조입니다.
    응답 구조 변경 가능성이 있습니다.
"""

import os
import re
import json
import time
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# ──────────────────────────────────────────────
# 환경변수 (선택적 소스)
# ──────────────────────────────────────────────
WORKNET_API_KEY  = os.getenv("WORKNET_API_KEY", "")
SARAMIN_API_KEY  = os.getenv("SARAMIN_API_KEY", "")
WORKNET_BASE_URL = "https://openapi.work24.go.kr/getJobInfo"
SARAMIN_BASE_URL = "https://oapi.saramin.co.kr/job-search"

# ──────────────────────────────────────────────
# 공통 요청 헤더  (스크래핑 차단 방지)
# ──────────────────────────────────────────────
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    "Accept":          "text/html,application/xhtml+xml,application/json,*/*;q=0.8",
}


# ══════════════════════════════════════════════
# 1. 원티드 비공식 JSON API
# ══════════════════════════════════════════════
# 파라미터 참고: 브라우저 DevTools → Network 탭 → XHR/Fetch 에서 확인
# 엔드포인트: https://www.wanted.co.kr/api/v4/jobs

_WANTED_URL = "https://www.wanted.co.kr/api/v4/jobs"

# 원티드 직무 카테고리 ID (초안 — 변경될 수 있음)
# 복수 선택: tag_type_ids=518,507,734 처럼 쉼표로 연결
WANTED_JOB_GROUPS = {
    "개발":      518,
    "디자인":    507,
    "기획/PM":   734,
    "마케팅":    789,
    "영업":      798,
    "경영지원":  939,
    "데이터":    655,
    "운영":      940,
}

# 원티드 지역 파라미터 (전국 검색 후 location 필드로 필터링하는 방식 사용)
# API 레벨 지역 필터는 코드가 자주 바뀌어 안정성이 낮음
_WANTED_REGION_MAP = {
    "서울": "서울특별시", "경기": "경기도", "인천": "인천광역시",
    "부산": "부산광역시", "대구": "대구광역시", "광주": "광주광역시",
    "대전": "대전광역시", "울산": "울산광역시",
}


def fetch_wanted_jobs(keyword: str, region: str = "",
                      experience: str = "", page: int = 1,
                      per_page: int = 100) -> list[dict]:
    """
    원티드 공개 JSON API로 채용 공고 수집

    Args:
        keyword:    검색 키워드
        region:     지역 (없으면 전국)
        experience: "신입" | "경력" | ""
        page:       페이지 번호 (1부터)
        per_page:   페이지당 결과 수 (최대 100)
    """
    # 경력 → years 파라미터 (신입=0, 경력=1~, 무관=-1)
    years_map = {"신입": "0", "경력": "1"}
    years     = years_map.get(experience, "-1")

    params = {
        "country":  "kr",
        "job_sort": "job.latest_order",   # 최신순 (job.rank_order: 인기순)
        "locations": "all",               # 전국 수집 후 region으로 후처리
        "years":    years,
        "limit":    min(per_page, 100),
        "offset":   (page - 1) * per_page,
        "query":    keyword,
    }

    headers = {**_HEADERS, "Referer": "https://www.wanted.co.kr/"}

    try:
        resp = requests.get(_WANTED_URL, params=params,
                            headers=headers, timeout=15)
        resp.raise_for_status()
        jobs = _parse_wanted_json(resp.json())

        # API 레벨 지역 필터 대신 location 문자열로 후처리
        if region:
            region_kw = _WANTED_REGION_MAP.get(region, region)
            jobs = [j for j in jobs if region_kw in j.get("location", "")
                    or not j.get("location")]   # 지역 미표기 공고는 포함
        return jobs

    except requests.RequestException as e:
        print(f"[원티드] API 호출 실패: {e}")
        return []
    except Exception as e:
        print(f"[원티드] 파싱 오류: {e}")
        return []


def _parse_wanted_json(data: dict) -> list[dict]:
    """원티드 JSON 응답 → 표준 공고 딕셔너리 리스트"""
    jobs = []
    for item in data.get("data", []):
        job_id  = item.get("id", "")
        company = item.get("company", {})
        address = item.get("address", {})

        # 마감일: "2026-07-31T00:00:00+09:00" → "2026-07-31"
        due_raw  = item.get("due_time") or ""
        deadline = due_raw[:10] if due_raw else ""

        # 경력 정보 (구조가 다를 수 있어 두 경로 모두 시도)
        exp_raw  = item.get("experience") or {}
        exp_text = exp_raw.get("name", "") if isinstance(exp_raw, dict) else str(exp_raw)

        # 기술 태그 → description에 포함
        tags     = item.get("job_tags", []) or []
        tag_text = ", ".join(t.get("title", "") for t in tags if t.get("title"))

        jobs.append({
            "source":       "원티드",
            "company":      company.get("name", ""),
            "title":        item.get("title", ""),
            "location":     (address.get("location") or
                             address.get("full_location", "")),
            "job_type":     "",   # 원티드 목록 API에는 고용형태 미포함
            "experience":   exp_text,
            "deadline":     deadline,
            "salary":       item.get("salary", "") or "",
            "description":  f"{item.get('title', '')} {tag_text}".strip(),
            "requirements": "",
            "preferred":    tag_text,
            "link":         f"https://www.wanted.co.kr/wd/{job_id}" if job_id else "",
            "posted_date":  (item.get("created_at") or "")[:10],
        })
    return jobs


# ══════════════════════════════════════════════
# 2. 잡코리아 HTML 스크래핑
# ══════════════════════════════════════════════
# URL: https://www.jobkorea.co.kr/Search/?stext={keyword}&tabType=recruit&Page_No={page}
#
# [셀렉터 유지보수 가이드]
# 파싱 실패 시:
#   1. output/jobkorea_debug.html 을 브라우저로 열기
#   2. 개발자 도구(F12)로 공고 목록 요소 확인
#   3. 아래 _JK_SELECTORS 딕셔너리 값 수정
# ──────────────────────────────────────────────
_JK_SEARCH_URL = "https://www.jobkorea.co.kr/Search/"

# 셀렉터를 한 곳에 모아 유지보수를 쉽게 함
_JK_SELECTORS = {
    # 공고 목록 컨테이너 (fallback 순서로 시도)
    "items": [
        "li.list-post",
        "article.list-item",
        "div.recruit-info",
        "li.recruit-info",
    ],
    # 회사명
    "company": [
        ".post-list-corp-name a",
        ".corp-name a",
        "p.name a",
        "a.corp-name",
    ],
    # 공고 제목 + href
    "title": [
        ".post-list-title a",
        "p.title a",
        "dt.title a",
        "h2.title a",
        "a.title",
    ],
    # 근무지·경력·고용형태 텍스트 셀
    "info_cells": [
        ".post-list-info span",
        ".list-info dd",
        "dl.info dd",
        "span.work-place",
    ],
    # 마감일
    "deadline": [
        ".post-date-info .date",
        ".end-date",
        "span.date",
        ".deadline",
    ],
    # 급여
    "salary": [
        ".salary",
        ".post-list-salary",
        "span.sal",
    ],
}

# 잡코리아 지역 파라미터 코드
_JK_REGION_CODE = {
    "서울": "101000", "경기": "102000", "인천": "108000",
    "부산": "106000", "대구": "103000", "광주": "104000",
    "대전": "105000", "울산": "107000", "강원": "109000",
    "충북": "110000", "충남": "111000", "전북": "112000",
    "전남": "113000", "경북": "114000", "경남": "115000",
    "제주": "116000", "세종": "118000",
}

# 잡코리아 경력 파라미터 코드
_JK_EXP_CODE = {"신입": "1", "경력": "2"}


def fetch_jobkorea_jobs(keyword: str, region: str = "",
                        experience: str = "", page: int = 1) -> list[dict]:
    """잡코리아 검색결과 HTML 스크래핑"""
    params: dict = {
        "stext":   keyword,
        "tabType": "recruit",
        "Page_No": page,
    }
    if region and region in _JK_REGION_CODE:
        params["local"] = _JK_REGION_CODE[region]
    if experience and experience in _JK_EXP_CODE:
        params["careerType"] = _JK_EXP_CODE[experience]

    headers = {**_HEADERS, "Referer": "https://www.jobkorea.co.kr/"}

    try:
        resp = requests.get(_JK_SEARCH_URL, params=params,
                            headers=headers, timeout=15)
        resp.raise_for_status()
        jobs = _parse_jobkorea_html(resp.text)

        # 파싱 결과 없을 때 디버그 HTML 저장
        if not jobs:
            _save_debug_html(resp.text, "jobkorea_debug.html")
            print("[잡코리아] 공고 파싱 결과 없음 → output/jobkorea_debug.html 확인")

        return jobs

    except requests.RequestException as e:
        print(f"[잡코리아] 요청 실패: {e}")
        return []
    except Exception as e:
        print(f"[잡코리아] 파싱 오류: {e}")
        return []


def _parse_jobkorea_html(html: str) -> list[dict]:
    """잡코리아 HTML → 표준 공고 딕셔너리 리스트"""
    soup  = BeautifulSoup(html, "lxml")
    jobs  = []

    # 공고 아이템 찾기 (fallback 순서로 시도)
    items = []
    for selector in _JK_SELECTORS["items"]:
        items = soup.select(selector)
        if items:
            break

    if not items:
        return []

    for item in items:
        try:
            # ── 회사명 ──
            company = _first_text(item, _JK_SELECTORS["company"])

            # ── 공고 제목 + 링크 ──
            title_el = _first_el(item, _JK_SELECTORS["title"])
            title    = title_el.get_text(strip=True) if title_el else ""
            href     = title_el.get("href", "") if title_el else ""
            if href.startswith("/"):
                link = f"https://www.jobkorea.co.kr{href}"
            elif href.startswith("http"):
                link = href
            else:
                link = ""

            if not title:
                continue

            # ── 근무지 / 경력 / 고용형태 ──
            info_cells = []
            for sel in _JK_SELECTORS["info_cells"]:
                cells = [el.get_text(strip=True) for el in item.select(sel)
                         if el.get_text(strip=True)]
                if cells:
                    info_cells = cells
                    break

            location   = info_cells[0] if len(info_cells) > 0 else ""
            exp_text   = info_cells[1] if len(info_cells) > 1 else ""
            job_type   = info_cells[2] if len(info_cells) > 2 else ""

            # ── 마감일 ──
            deadline_raw = _first_text(item, _JK_SELECTORS["deadline"])
            deadline     = _parse_jk_date(deadline_raw)

            # ── 급여 ──
            salary = _first_text(item, _JK_SELECTORS["salary"])

            jobs.append({
                "source":       "잡코리아",
                "company":      company,
                "title":        title,
                "location":     location,
                "job_type":     job_type,
                "experience":   exp_text,
                "deadline":     deadline,
                "salary":       salary,
                "description":  f"{title} {exp_text}".strip(),
                "requirements": "",
                "preferred":    "",
                "link":         link,
                "posted_date":  "",
            })
        except Exception:
            continue

    return jobs


def _first_el(parent, selectors: list):
    """여러 셀렉터 중 처음으로 매칭되는 요소 반환"""
    for sel in selectors:
        el = parent.select_one(sel)
        if el:
            return el
    return None


def _first_text(parent, selectors: list) -> str:
    """여러 셀렉터 중 처음으로 매칭되는 텍스트 반환"""
    el = _first_el(parent, selectors)
    return el.get_text(strip=True) if el else ""


def _parse_jk_date(raw: str) -> str:
    """잡코리아 날짜 텍스트 → YYYY-MM-DD"""
    if not raw:
        return ""
    raw = raw.strip()
    if raw in ("상시채용", "채용시", "수시채용", "상시"):
        return ""                    # data_parser가 '상시채용'으로 처리

    # 형식 1: 2026.06.30  /  26.06.30  /  2026-06-30
    m = re.search(r"(\d{2,4})[.\-](\d{1,2})[.\-](\d{1,2})", raw)
    if m:
        y, mo, d = m.group(1), m.group(2).zfill(2), m.group(3).zfill(2)
        if len(y) == 2:
            y = "20" + y
        return f"{y}-{mo}-{d}"

    # 형식 2: 06.30  /  06/30  (연도 없음 → 올해)
    m2 = re.search(r"(\d{1,2})[./](\d{1,2})", raw)
    if m2:
        year = datetime.now().year
        return f"{year}-{m2.group(1).zfill(2)}-{m2.group(2).zfill(2)}"

    return ""


def _save_debug_html(html: str, filename: str) -> None:
    """디버그용 HTML 파일 저장"""
    os.makedirs("output", exist_ok=True)
    path = os.path.join("output", filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


# ══════════════════════════════════════════════
# 3. 워크넷 공공 API  (선택적 보조 소스)
# ══════════════════════════════════════════════
def fetch_worknet_jobs(keyword: str, region: str = "", job_type: str = "",
                       experience: str = "", page: int = 1,
                       per_page: int = 100) -> list[dict]:
    if not WORKNET_API_KEY or WORKNET_API_KEY == "여기에_워크넷_API키_입력":
        return []

    region_code_map = {
        "서울": "I100", "경기": "I200", "인천": "I300",
        "부산": "I400", "대구": "I500", "광주": "I600",
        "대전": "I700", "울산": "I800", "강원": "I900",
        "충북": "J000", "충남": "J100", "전북": "J200",
        "전남": "J300", "경북": "J400", "경남": "J500",
        "제주": "J600", "세종": "J700",
    }
    job_type_code_map = {"정규직": "10", "계약직": "20", "인턴": "30", "아르바이트": "50"}
    exp_code_map      = {"신입": "0", "경력": "1"}

    params = {
        "authKey":    WORKNET_API_KEY,
        "callTp":     "L",
        "returnType": "XML",
        "keyword":    keyword,
        "pageNo":     str(page),
        "display":    str(per_page),
    }
    if region     in region_code_map:    params["region"]   = region_code_map[region]
    if job_type   in job_type_code_map:  params["empTpCd"]  = job_type_code_map[job_type]
    if experience in exp_code_map:       params["career"]   = exp_code_map[experience]

    try:
        resp = requests.get(WORKNET_BASE_URL, params=params, timeout=15)
        resp.raise_for_status()
        return _parse_worknet_xml(resp.text)
    except Exception as e:
        print(f"[워크넷] 호출 실패: {e}")
        return []


def _parse_worknet_xml(xml_text: str) -> list[dict]:
    jobs = []
    try:
        root = ET.fromstring(xml_text)
        for item in root.findall(".//item"):
            job = {
                "source":       "워크넷",
                "company":      _get_text(item, "cmpnyNm"),
                "title":        _get_text(item, "jobNm"),
                "location":     _get_text(item, "workRegionNm"),
                "job_type":     _get_text(item, "empTpNm"),
                "experience":   _get_text(item, "careerCondNm"),
                "deadline":     _get_text(item, "rcptCloseDt"),
                "salary":       _get_text(item, "sal"),
                "description":  _get_text(item, "jobDesc"),
                "requirements": _get_text(item, "qlfcCond"),
                "preferred":    _get_text(item, "prefCond"),
                "link":         _get_text(item, "wantedAuthNo"),
                "posted_date":  _get_text(item, "postDt"),
            }
            if job["link"]:
                job["link"] = (
                    f"https://www.work24.go.kr/wk/a/b/1200/sjDetailView.do"
                    f"?wantedAuthNo={job['link']}"
                )
            jobs.append(job)
    except ET.ParseError as e:
        print(f"[워크넷] XML 파싱 실패: {e}")
    return jobs


def _get_text(element, tag: str) -> str:
    node = element.find(tag)
    return node.text.strip() if node is not None and node.text else ""


# ══════════════════════════════════════════════
# 4. 사람인 공식 API  (선택적 보조 소스)
# ══════════════════════════════════════════════
def fetch_saramin_jobs(keyword: str, region: str = "",
                       experience: str = "", page: int = 1,
                       per_page: int = 100) -> list[dict]:
    if not SARAMIN_API_KEY or SARAMIN_API_KEY == "여기에_사람인_API키_입력":
        return []

    region_code_map = {
        "서울": "101000", "경기": "102000", "인천": "108000",
        "부산": "106000", "대구": "103000", "광주": "104000",
        "대전": "105000", "울산": "107000", "세종": "118000",
        "강원": "109000", "충북": "110000", "충남": "111000",
        "전북": "112000", "전남": "113000", "경북": "114000",
        "경남": "115000", "제주": "116000",
    }
    params = {
        "access-key": SARAMIN_API_KEY,
        "keywords":   keyword,
        "start":      (page - 1) * per_page,
        "count":      min(per_page, 110),
        "fields":     "posting-date,expiration-date,salary,company,experience-level,job-type,location",
    }
    if region     in region_code_map:   params["loc_cd"] = region_code_map[region]
    if experience == "신입":            params["exp_cd"] = "1"
    elif experience == "경력":          params["exp_cd"] = "2"

    try:
        resp = requests.get(SARAMIN_BASE_URL, params=params, timeout=15)
        resp.raise_for_status()
        return _parse_saramin_json(resp.json())
    except Exception as e:
        print(f"[사람인] 호출 실패: {e}")
        return []


def _parse_saramin_json(data: dict) -> list[dict]:
    jobs = []
    try:
        job_list = data.get("jobs", {}).get("job", [])
        if not isinstance(job_list, list):
            job_list = [job_list]
        for item in job_list:
            position = item.get("position", {})
            company  = item.get("company", {}).get("detail", {})
            exp_ts   = item.get("expiration-timestamp", "")
            if exp_ts:
                try:
                    deadline = datetime.fromtimestamp(int(exp_ts)).strftime("%Y-%m-%d")
                except Exception:
                    deadline = item.get("expiration-date", "")
            else:
                deadline = item.get("expiration-date", "")

            jobs.append({
                "source":       "사람인",
                "company":      company.get("name", ""),
                "title":        position.get("title", ""),
                "location":     position.get("location", {}).get("name", ""),
                "job_type":     position.get("job-type", {}).get("name", ""),
                "experience":   position.get("experience-level", {}).get("name", ""),
                "deadline":     deadline,
                "salary":       item.get("salary", {}).get("name", ""),
                "description":  position.get("title", ""),
                "requirements": "",
                "preferred":    "",
                "link":         item.get("url", ""),
                "posted_date":  item.get("posting-date", ""),
            })
    except Exception as e:
        print(f"[사람인] JSON 파싱 오류: {e}")
    return jobs


# ══════════════════════════════════════════════
# 메인 수집 함수
# ══════════════════════════════════════════════
def collect_all_jobs(config: dict) -> list[dict]:
    """
    설정 기반 전체 공고 수집

    활성 소스:
      - 원티드 (기본)
      - 잡코리아 (기본)
      - 워크넷 (WORKNET_API_KEY 설정 시)
      - 사람인 (SARAMIN_API_KEY 설정 시)
    """
    keyword    = config["search"]["keyword"]
    region     = config["search"].get("region", "")
    job_type   = config["search"].get("job_type", "")
    experience = config["search"].get("experience", "")
    all_jobs: list[dict] = []

    # ── 1. 원티드 ──────────────────────────────
    print(f"[1/4] 원티드 수집 중... 키워드: '{keyword}'")
    wanted = fetch_wanted_jobs(keyword, region, experience, page=1, per_page=100)
    # 100개 꽉 찬 경우 추가 페이지 (최대 2페이지 추가)
    for p in range(2, 4):
        if len(wanted) % 100 != 0:
            break
        time.sleep(0.7)
        more = fetch_wanted_jobs(keyword, region, experience, page=p, per_page=100)
        if not more:
            break
        wanted.extend(more)
    print(f"      → {len(wanted)}개 수집")
    all_jobs.extend(wanted)

    # ── 2. 잡코리아 ────────────────────────────
    time.sleep(1.0)   # 서버 부하 분산
    print(f"[2/4] 잡코리아 스크래핑 중... 키워드: '{keyword}'")
    jk_jobs = fetch_jobkorea_jobs(keyword, region, experience, page=1)
    # 결과가 있으면 최대 4페이지 추가 수집
    for p in range(2, 6):
        if not jk_jobs or len(jk_jobs) < (p - 1) * 15:
            break
        time.sleep(1.0)
        more = fetch_jobkorea_jobs(keyword, region, experience, page=p)
        if not more:
            break
        jk_jobs.extend(more)
    print(f"      → {len(jk_jobs)}개 수집")
    all_jobs.extend(jk_jobs)

    # ── 3. 워크넷 (API 키 있을 때만) ──────────
    if WORKNET_API_KEY and WORKNET_API_KEY != "여기에_워크넷_API키_입력":
        time.sleep(0.5)
        print(f"[3/4] 워크넷 수집 중...")
        wn = fetch_worknet_jobs(keyword, region, job_type, experience)
        for p in range(2, 4):
            if len(wn) % 100 != 0:
                break
            time.sleep(0.5)
            more = fetch_worknet_jobs(keyword, region, job_type, experience, page=p)
            if not more:
                break
            wn.extend(more)
        print(f"      → {len(wn)}개 수집")
        all_jobs.extend(wn)
    else:
        print("[3/4] 워크넷 건너뜀 (API 키 미설정)")

    # ── 4. 사람인 (API 키 있을 때만) ──────────
    if SARAMIN_API_KEY and SARAMIN_API_KEY != "여기에_사람인_API키_입력":
        time.sleep(0.5)
        print(f"[4/4] 사람인 수집 중...")
        sr = fetch_saramin_jobs(keyword, region, experience)
        print(f"      → {len(sr)}개 수집")
        all_jobs.extend(sr)
    else:
        print("[4/4] 사람인 건너뜀 (API 키 미설정)")

    # ── 결과 없을 때 샘플 데이터로 폴백 ────────
    if not all_jobs:
        print("[경고] 수집된 공고 없음 → 샘플 데이터 사용")
        return _load_sample_data()

    print(f"\n[수집 완료] 총 {len(all_jobs)}개 (원티드 {len(wanted)} | "
          f"잡코리아 {len(jk_jobs)} | 기타 {len(all_jobs) - len(wanted) - len(jk_jobs)})")
    return all_jobs


# ══════════════════════════════════════════════
# 샘플 데이터 폴백
# ══════════════════════════════════════════════
def _load_sample_data() -> list[dict]:
    sample_path = os.path.join(os.path.dirname(__file__), "sample_jobs.json")
    if os.path.exists(sample_path):
        with open(sample_path, encoding="utf-8") as f:
            return json.load(f)

    return [
        {
            "source": "샘플", "company": "(주)테크스타트",
            "title": "Python 백엔드 개발자", "location": "서울 강남구",
            "job_type": "정규직", "experience": "신입",
            "deadline": "2026-06-30", "salary": "3,000만원 ~ 4,000만원",
            "description": "Python Django 기반 백엔드 개발. REST API 설계 및 구현.",
            "requirements": "Python 개발 경험, SQL 기초 지식",
            "preferred": "Django, Flask 경험자, AWS 경험자",
            "link": "https://www.wanted.co.kr", "posted_date": "2026-05-01",
        },
        {
            "source": "샘플", "company": "데이터드림(주)",
            "title": "데이터 분석가 (신입)", "location": "서울 마포구",
            "job_type": "정규직", "experience": "신입",
            "deadline": "2026-07-20", "salary": "2,800만원 ~ 3,500만원",
            "description": "데이터 수집 및 분석, 시각화 대시보드 제작.",
            "requirements": "Python, SQL 활용 가능자",
            "preferred": "Pandas, Tableau 경험자",
            "link": "https://www.wanted.co.kr", "posted_date": "2026-05-10",
        },
        {
            "source": "샘플", "company": "클라우드넷(주)",
            "title": "풀스택 개발자 (React + Python)", "location": "경기 성남시",
            "job_type": "정규직", "experience": "신입",
            "deadline": "2026-07-15", "salary": "3,500만원 ~ 4,500만원",
            "description": "React 프론트엔드 및 Python FastAPI 백엔드 개발.",
            "requirements": "Python 또는 JavaScript 개발 경험",
            "preferred": "AWS 자격증, Docker 경험자",
            "link": "https://www.wanted.co.kr", "posted_date": "2026-05-12",
        },
    ]
