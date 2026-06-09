"""
ai_generator.py
공고 기반 자기소개서 포인트 및 예상 면접 질문 생성 모듈

우선순위:
  1. ANTHROPIC_API_KEY 설정 시 → Claude API (claude-haiku-4-5-20251001) 사용
  2. API 키 미설정 또는 호출 실패 시 → 템플릿 기반 폴백
"""

import os
import re
import json
import logging

from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
logger = logging.getLogger(__name__)


# ============================================================
# Claude API 기반 생성 (기능 4)
# ============================================================
def _ai_generate_claude(job: dict) -> tuple[list[str], list[str]]:
    """Claude API로 자소서 포인트·면접 질문 생성 (프롬프트 캐싱 적용)"""
    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic 패키지 미설치. pip install anthropic")
        return [], []

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    job_summary = (
        f"회사: {job.get('company', '')}\n"
        f"직무: {job.get('title', '')}\n"
        f"지역: {job.get('location', '')}\n"
        f"경력: {job.get('experience', '')}\n"
        f"기술키워드: {', '.join(job.get('tech_keywords', []))}\n"
        f"자격요건: {job.get('requirements', '')[:400]}\n"
        f"우대사항: {job.get('preferred', '')[:300]}\n"
        f"공고내용: {job.get('description', '')[:500]}"
    ).strip()

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=[
                {
                    "type": "text",
                    "text": (
                        "당신은 취업 전문 컨설턴트입니다. 채용공고를 분석하여 "
                        "맞춤형 자기소개서 작성 포인트와 예상 면접 질문을 한국어로 생성합니다.\n"
                        "규칙:\n"
                        "- 반드시 순수 JSON만 응답 (다른 텍스트 없이)\n"
                        "- cover_letter_points: 최대 8개, 구체적이고 실용적인 작성 가이드\n"
                        "- interview_questions: 최대 12개, 기술+인성 균형\n"
                        "- 각 항목은 완성된 한국어 문장으로 작성"
                    ),
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"다음 채용공고를 분석해 주세요:\n\n{job_summary}\n\n"
                        '응답 형식:\n'
                        '{"cover_letter_points": ["포인트1", ...], '
                        '"interview_questions": ["질문1", ...]}'
                    ),
                }
            ],
        )

        text = response.content[0].text.strip()
        # 마크다운 코드 블록 제거
        text = re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
        data = json.loads(text)
        return (
            data.get("cover_letter_points", [])[:8],
            data.get("interview_questions", [])[:12],
        )

    except json.JSONDecodeError:
        logger.warning("Claude 응답 JSON 파싱 실패, 템플릿 폴백 사용")
        return [], []
    except Exception as e:
        logger.warning(f"Claude API 호출 실패: {e}, 템플릿 폴백 사용")
        return [], []


# ============================================================
# 템플릿 기반 생성 (폴백)
# ============================================================
def generate_cover_letter_points(job: dict) -> list[str]:
    """공고 기반 자기소개서 작성 포인트 생성 (템플릿)"""
    points = []
    title        = job.get("title", "")
    requirements = job.get("requirements", "")
    preferred    = job.get("preferred", "")
    tech_keywords = job.get("tech_keywords", [])
    company      = job.get("company", "")

    if tech_keywords:
        kw_str = ", ".join(tech_keywords[:5])
        points.append(
            f"[기술역량] {kw_str} 관련 프로젝트 경험 또는 학습 내용을 구체적인 수치와 함께 서술하세요."
        )

    if requirements:
        for req in _extract_key_phrases(requirements)[:3]:
            points.append(f"[자격요건 대응] '{req}'에 해당하는 본인의 경험을 STAR 기법으로 작성하세요.")

    if preferred:
        for pref in _extract_key_phrases(preferred)[:2]:
            points.append(f"[우대사항 어필] '{pref}' 역량을 보유하고 있다면 적극적으로 강조하세요.")

    if "데이터" in title or "분석" in title:
        points.append("[직무연관] 데이터 분석 프로젝트에서 인사이트를 도출한 경험과 그 영향을 서술하세요.")
    if "백엔드" in title or "서버" in title or "개발" in title:
        points.append("[직무연관] 실제 서비스를 배포하거나 API를 설계·구현한 경험을 구체적으로 작성하세요.")
    if "풀스택" in title:
        points.append("[직무연관] 프론트엔드와 백엔드를 모두 다룬 경험을 강조하고, 협업 역량을 어필하세요.")

    points.append(f"[지원동기] {company}의 사업 분야와 서비스를 조사하여 구체적인 지원 동기를 작성하세요.")
    points.append("[성장가능성] 입사 후 3~5년 내 본인이 기여하고 싶은 목표를 직무와 연결하여 서술하세요.")

    return points[:8]


def generate_interview_questions(job: dict) -> list[str]:
    """공고 기반 예상 면접 질문 생성 (템플릿)"""
    questions = []
    title        = job.get("title", "")
    tech_keywords = job.get("tech_keywords", [])
    company      = job.get("company", "")

    questions += [
        "1분 자기소개를 해주세요.",
        f"{company}에 지원한 이유가 무엇인가요?",
        "본인의 강점과 약점을 말씀해 주세요.",
        "팀 프로젝트에서 갈등이 생겼을 때 어떻게 해결했나요?",
        "입사 후 첫 3개월 동안 어떤 일을 하고 싶으신가요?",
    ]

    tech_q_map = {
        "Python":  "Python에서 GIL(Global Interpreter Lock)이란 무엇이며, 멀티스레딩에 어떤 영향을 미치나요?",
        "Django":  "Django의 MVT 패턴을 설명하고, ORM을 사용해본 경험을 말씀해 주세요.",
        "FastAPI": "FastAPI와 Django의 차이점은 무엇이며, 언제 FastAPI를 선택하시겠나요?",
        "SQL":     "SQL 조인(JOIN)의 종류와 차이점을 설명해 주세요.",
        "React":   "React에서 Virtual DOM이 동작하는 방식을 설명해 주세요.",
        "AWS":     "AWS S3, EC2, RDS의 역할과 차이점을 설명해 주세요.",
        "Docker":  "Docker 컨테이너와 VM(가상머신)의 차이점은 무엇인가요?",
        "Git":     "Git rebase와 merge의 차이점을 설명하고, 언제 rebase를 사용하나요?",
        "Pandas":  "Pandas DataFrame에서 결측값을 처리하는 방법을 설명해 주세요.",
    }

    for kw in tech_keywords[:4]:
        if kw in tech_q_map:
            questions.append(f"[기술] {tech_q_map[kw]}")
        else:
            questions.append(f"[기술] {kw}를 사용한 프로젝트 경험과 어려웠던 점을 말씀해 주세요.")

    if "데이터" in title or "분석" in title:
        questions += [
            "[직무] 분석 결과를 비개발자에게 설명해야 할 때 어떻게 커뮤니케이션하나요?",
            "[직무] 데이터 품질 이슈를 발견했을 때 어떻게 처리하나요?",
        ]
    if "백엔드" in title or "서버" in title:
        questions += [
            "[직무] RESTful API 설계 원칙에 대해 설명해 주세요.",
            "[직무] 서비스 응답 속도가 느릴 때 어떤 방법으로 원인을 파악하고 개선하나요?",
        ]
    if "신입" in job.get("experience", ""):
        questions += [
            "[신입] 가장 인상 깊었던 개인/팀 프로젝트와 본인의 기여를 설명해 주세요.",
            "[신입] 학교에서 배운 내용 중 이 직무에 가장 도움이 될 것 같은 것은 무엇인가요?",
        ]

    seen, unique = set(), []
    for q in questions:
        if q not in seen:
            seen.add(q)
            unique.append(q)
    return unique[:12]


def _extract_key_phrases(text: str, max_items: int = 5) -> list[str]:
    items = re.split(r"[\n•·,，/]", text)
    return [i.strip() for i in items if len(i.strip()) > 4][:max_items]


# ============================================================
# 공개 인터페이스
# ============================================================
def add_ai_content(jobs: list[dict]) -> list[dict]:
    """전체 공고 리스트에 자소서 포인트·면접 질문 추가"""
    use_claude = bool(
        ANTHROPIC_API_KEY and ANTHROPIC_API_KEY != "여기에_Claude_API키_입력"
    )
    if use_claude:
        print("[AI] Claude API로 자소서·면접 질문 생성 중...")
    else:
        print("[AI] 템플릿 기반으로 자소서·면접 질문 생성 중... (Claude API 키 미설정)")

    for job in jobs:
        cl_points, cl_questions = [], []

        if use_claude:
            cl_points, cl_questions = _ai_generate_claude(job)

        # Claude 결과가 비어 있으면 템플릿 폴백
        job["cover_letter_points"] = cl_points or generate_cover_letter_points(job)
        job["interview_questions"] = cl_questions or generate_interview_questions(job)

    return jobs
