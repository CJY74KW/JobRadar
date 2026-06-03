"""
api_collector.py
채용정보 API 호출 및 공고 데이터 수집 모듈
- 워크넷(고용24) 공공데이터 API 기반
- 사람인 API 확장 연동 구조 포함
"""

import os
import json
import time
import requests
import xml.etree.ElementTree as ET
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# 워크넷 API 설정
# 발급처: https://www.data.go.kr → '고용24 채용정보 서비스' 검색
# ============================================================
WORKNET_API_KEY = os.getenv("WORKNET_API_KEY", "")
WORKNET_BASE_URL = "https://openapi.work24.go.kr/getJobInfo"

# ============================================================
# 사람인 API 설정 (확장용 — API키 발급 후 활성화)
# ============================================================
# SARAMIN_API_KEY = os.getenv("SARAMIN_API_KEY", "")
# SARAMIN_BASE_URL = "https://oapi.saramin.co.kr/job-search"


def fetch_worknet_jobs(keyword: str, region: str = "", job_type: str = "",
                       experience: str = "", page: int = 1, per_page: int = 100) -> list[dict]:
    """
    워크넷 채용정보 API 호출
    :return: 공고 딕셔너리 리스트
    """
    if not WORKNET_API_KEY or WORKNET_API_KEY == "여기에_워크넷_API키_입력":
        print("[경고] WORKNET_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
        return _load_sample_data()

    # 지역코드 매핑 (워크넷 API 규격)
    region_code_map = {
        "서울": "I100",
        "경기": "I200",
        "인천": "I300",
        "부산": "I400",
        "대구": "I500",
        "광주": "I600",
        "대전": "I700",
        "울산": "I800",
        "강원": "I900",
        "충북": "J000",
        "충남": "J100",
        "전북": "J200",
        "전남": "J300",
        "경북": "J400",
        "경남": "J500",
        "제주": "J600",
        "세종": "J700",
    }

    # 고용형태코드 매핑
    job_type_code_map = {
        "정규직": "10",
        "계약직": "20",
        "인턴": "30",
        "파견직": "40",
        "아르바이트": "50",
    }

    # 경력코드 매핑
    exp_code_map = {
        "신입": "0",
        "경력": "1",
        "무관": "",
    }

    params = {
        "authKey": WORKNET_API_KEY,
        "callTp": "L",           # L: 목록, D: 상세
        "returnType": "XML",
        "keyword": keyword,
        "pageNo": str(page),
        "display": str(per_page),
    }

    if region and region in region_code_map:
        params["region"] = region_code_map[region]
    if job_type and job_type in job_type_code_map:
        params["empTpCd"] = job_type_code_map[job_type]
    if experience and experience in exp_code_map and exp_code_map[experience]:
        params["career"] = exp_code_map[experience]

    try:
        response = requests.get(WORKNET_BASE_URL, params=params, timeout=15)
        response.raise_for_status()
        return _parse_worknet_xml(response.text)
    except requests.exceptions.ConnectionError:
        print("[오류] 네트워크 연결 실패. 샘플 데이터를 사용합니다.")
        return _load_sample_data()
    except requests.exceptions.Timeout:
        print("[오류] API 요청 시간 초과. 샘플 데이터를 사용합니다.")
        return _load_sample_data()
    except Exception as e:
        print(f"[오류] API 호출 실패: {e}")
        return _load_sample_data()


def _parse_worknet_xml(xml_text: str) -> list[dict]:
    """워크넷 XML 응답 파싱"""
    jobs = []
    try:
        root = ET.fromstring(xml_text)
        for item in root.findall(".//item"):
            job = {
                "source": "워크넷",
                "company": _get_text(item, "cmpnyNm"),
                "title": _get_text(item, "jobNm"),
                "location": _get_text(item, "workRegionNm"),
                "job_type": _get_text(item, "empTpNm"),
                "experience": _get_text(item, "careerCondNm"),
                "deadline": _get_text(item, "rcptCloseDt"),
                "salary": _get_text(item, "sal"),
                "description": _get_text(item, "jobDesc"),
                "requirements": _get_text(item, "qlfcCond"),
                "preferred": _get_text(item, "prefCond"),
                "link": _get_text(item, "wantedAuthNo"),
                "posted_date": _get_text(item, "postDt"),
            }
            # 워크넷 공고 링크 조합
            if job["link"]:
                job["link"] = f"https://www.work24.go.kr/wk/a/b/1200/sjDetailView.do?wantedAuthNo={job['link']}"
            jobs.append(job)
    except ET.ParseError as e:
        print(f"[오류] XML 파싱 실패: {e}")
    return jobs


def _get_text(element, tag: str) -> str:
    node = element.find(tag)
    return node.text.strip() if node is not None and node.text else ""


# ============================================================
# 사람인 API 수집 함수 (확장용 — 현재 주석 처리)
# API키 발급 후 아래 함수 주석 해제하여 사용
# ============================================================
# def fetch_saramin_jobs(keyword: str, region: str = "", page: int = 1) -> list[dict]:
#     params = {
#         "access-key": SARAMIN_API_KEY,
#         "keywords": keyword,
#         "job_type": 1,
#         "start": (page - 1) * 10,
#         "count": 10,
#         "fields": "posting-date,expiration-date,job-title,salary,company,experience-level,required-education-level",
#     }
#     response = requests.get(SARAMIN_BASE_URL, params=params, timeout=15)
#     return _parse_saramin_json(response.json())


def collect_all_jobs(config: dict) -> list[dict]:
    """설정 파일 기반 전체 공고 수집"""
    keyword = config["search"]["keyword"]
    region = config["search"].get("region", "")
    job_type = config["search"].get("job_type", "")
    experience = config["search"].get("experience", "")

    print(f"[수집] 워크넷 API 호출 중... 키워드: '{keyword}', 지역: '{region}'")
    jobs = fetch_worknet_jobs(keyword, region, job_type, experience, page=1, per_page=100)

    # 페이지가 많을 경우 추가 수집 (최대 3페이지)
    if len(jobs) == 100:
        for page in range(2, 4):
            time.sleep(0.5)
            more = fetch_worknet_jobs(keyword, region, job_type, experience, page=page, per_page=100)
            if not more:
                break
            jobs.extend(more)

    # 확장: 사람인 API 병합 (주석 해제 후 사용)
    # saramin_jobs = fetch_saramin_jobs(keyword, region)
    # jobs.extend(saramin_jobs)

    print(f"[수집 완료] 총 {len(jobs)}개 공고 수집")
    return jobs


def _load_sample_data() -> list[dict]:
    """API 키 미설정 시 사용할 샘플 데이터"""
    sample_path = os.path.join(os.path.dirname(__file__), "sample_jobs.json")
    if os.path.exists(sample_path):
        with open(sample_path, encoding="utf-8") as f:
            return json.load(f)

    # 인라인 샘플 데이터 (파일 없을 때 fallback)
    return [
        {
            "source": "샘플",
            "company": "(주)테크스타트",
            "title": "Python 백엔드 개발자",
            "location": "서울 강남구",
            "job_type": "정규직",
            "experience": "신입",
            "deadline": "2026-06-30",
            "salary": "3,000만원 ~ 4,000만원",
            "description": "Python Django 기반 백엔드 개발. REST API 설계 및 구현. AWS 클라우드 환경 운영.",
            "requirements": "Python 개발 경험, SQL 기초 지식, Git 사용 가능자",
            "preferred": "Django, Flask 경험자, AWS 경험자, 데이터 분석 경험자",
            "link": "https://www.work24.go.kr",
            "posted_date": "2026-05-01",
        },
        {
            "source": "샘플",
            "company": "데이터드림(주)",
            "title": "데이터 분석가 (신입)",
            "location": "서울 마포구",
            "job_type": "정규직",
            "experience": "신입",
            "deadline": "2026-05-20",
            "salary": "2,800만원 ~ 3,500만원",
            "description": "데이터 수집 및 분석, 시각화 대시보드 제작, SQL 기반 리포트 작성.",
            "requirements": "Python, SQL 활용 가능자, 통계 기초 지식",
            "preferred": "Pandas, Tableau 경험자, 공모전 수상자",
            "link": "https://www.work24.go.kr",
            "posted_date": "2026-05-10",
        },
        {
            "source": "샘플",
            "company": "클라우드넷(주)",
            "title": "풀스택 개발자 (React + Python)",
            "location": "경기 성남시",
            "job_type": "정규직",
            "experience": "신입",
            "deadline": "2026-07-15",
            "salary": "3,500만원 ~ 4,500만원",
            "description": "React 프론트엔드 및 Python FastAPI 백엔드 개발. AWS 인프라 구성.",
            "requirements": "Python 또는 JavaScript 개발 경험, React 기본 이해",
            "preferred": "AWS 자격증, Docker 경험자",
            "link": "https://www.work24.go.kr",
            "posted_date": "2026-05-12",
        },
    ]
