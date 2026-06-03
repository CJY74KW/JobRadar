"""
ai_generator.py
공고 기반 자기소개서 작성 포인트 및 예상 면접 질문 자동 생성 모듈
- 공고의 직무 내용·자격 요건·기술 키워드를 분석하여 생성
- 템플릿 기반(API 불필요) 방식으로 구현
"""

import re


def generate_cover_letter_points(job: dict) -> list[str]:
    """공고 기반 자기소개서 작성 포인트 생성"""
    points = []
    title = job.get("title", "")
    requirements = job.get("requirements", "")
    preferred = job.get("preferred", "")
    tech_keywords = job.get("tech_keywords", [])
    company = job.get("company", "")

    # 1. 핵심 기술 스택 강조 포인트
    if tech_keywords:
        kw_str = ", ".join(tech_keywords[:5])
        points.append(
            f"[기술역량] {kw_str} 관련 프로젝트 경험 또는 학습 내용을 구체적인 수치와 함께 서술하세요."
        )

    # 2. 자격 요건 기반 포인트
    if requirements:
        key_reqs = _extract_key_phrases(requirements)
        for req in key_reqs[:3]:
            points.append(f"[자격요건 대응] '{req}'에 해당하는 본인의 경험을 STAR 기법으로 작성하세요.")

    # 3. 우대 사항 기반 포인트
    if preferred:
        pref_items = _extract_key_phrases(preferred)
        for pref in pref_items[:2]:
            points.append(f"[우대사항 어필] '{pref}' 역량을 보유하고 있다면 적극적으로 강조하세요.")

    # 4. 직무명 기반 범용 포인트
    if "데이터" in title or "분석" in title:
        points.append("[직무연관] 데이터 분석 프로젝트에서 인사이트를 도출한 경험과 그 영향을 서술하세요.")
    if "백엔드" in title or "서버" in title or "개발" in title:
        points.append("[직무연관] 실제 서비스를 배포하거나 API를 설계·구현한 경험을 구체적으로 작성하세요.")
    if "풀스택" in title:
        points.append("[직무연관] 프론트엔드와 백엔드를 모두 다룬 경험을 강조하고, 협업 역량을 어필하세요.")

    # 5. 회사 관련 포인트
    points.append(f"[지원동기] {company}의 사업 분야와 서비스를 조사하여 구체적인 지원 동기를 작성하세요.")
    points.append("[성장가능성] 입사 후 3~5년 내 본인이 기여하고 싶은 목표를 직무와 연결하여 서술하세요.")

    return points[:8]  # 최대 8개 반환


def generate_interview_questions(job: dict) -> list[str]:
    """공고 기반 예상 면접 질문 생성"""
    questions = []
    title = job.get("title", "")
    tech_keywords = job.get("tech_keywords", [])
    requirements = job.get("requirements", "")
    company = job.get("company", "")

    # 1. 공통 면접 질문
    questions += [
        f"1분 자기소개를 해주세요.",
        f"{company}에 지원한 이유가 무엇인가요?",
        "본인의 강점과 약점을 말씀해 주세요.",
        "팀 프로젝트에서 갈등이 생겼을 때 어떻게 해결했나요?",
        "입사 후 첫 3개월 동안 어떤 일을 하고 싶으신가요?",
    ]

    # 2. 기술 면접 질문 (키워드 기반)
    tech_q_map = {
        "Python": "Python에서 GIL(Global Interpreter Lock)이란 무엇이며, 멀티스레딩에 어떤 영향을 미치나요?",
        "Django": "Django의 MVT 패턴을 설명하고, ORM을 사용해본 경험을 말씀해 주세요.",
        "FastAPI": "FastAPI와 Django의 차이점은 무엇이며, 언제 FastAPI를 선택하시겠나요?",
        "SQL": "SQL 조인(JOIN)의 종류와 차이점을 설명해 주세요.",
        "React": "React에서 Virtual DOM이 동작하는 방식을 설명해 주세요.",
        "AWS": "AWS S3, EC2, RDS의 역할과 차이점을 설명해 주세요.",
        "Docker": "Docker 컨테이너와 VM(가상머신)의 차이점은 무엇인가요?",
        "Git": "Git rebase와 merge의 차이점을 설명하고, 언제 rebase를 사용하나요?",
        "Pandas": "Pandas DataFrame에서 결측값을 처리하는 방법을 설명해 주세요.",
        "Machine Learning": "과적합(Overfitting)을 방지하기 위한 방법들을 설명해 주세요.",
    }

    for kw in tech_keywords[:4]:
        if kw in tech_q_map:
            questions.append(f"[기술] {tech_q_map[kw]}")
        else:
            questions.append(f"[기술] {kw}를 사용한 프로젝트 경험과 어려웠던 점을 말씀해 주세요.")

    # 3. 직무별 추가 질문
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

    # 중복 제거 후 최대 12개 반환
    seen = set()
    unique = []
    for q in questions:
        if q not in seen:
            seen.add(q)
            unique.append(q)

    return unique[:12]


def _extract_key_phrases(text: str, max_items: int = 5) -> list[str]:
    """자격요건·우대사항 텍스트에서 핵심 구문 추출"""
    # 줄바꿈·bullet 기호 기준으로 분리
    items = re.split(r"[\n•·,，/]", text)
    cleaned = [i.strip() for i in items if len(i.strip()) > 4]
    return cleaned[:max_items]


def add_ai_content(jobs: list[dict]) -> list[dict]:
    """전체 공고 리스트에 자소서 포인트·면접 질문 추가"""
    for job in jobs:
        job["cover_letter_points"] = generate_cover_letter_points(job)
        job["interview_questions"] = generate_interview_questions(job)
    return jobs
