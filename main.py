"""
main.py
취업 정보 자동화 시스템 메인 실행 파일

실행 방법:
    python main.py

사전 준비:
    1. .env 파일에 API 키 및 이메일 설정 입력
    2. config.json에서 희망 직무·지역·기술 스택 설정
    3. pip install -r requirements.txt
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

import json
import os
from dotenv import load_dotenv

from api_collector import collect_all_jobs
from data_parser import parse_and_clean, filter_expired, filter_deadline_soon
from analyzer import score_jobs, filter_by_user_tech, get_recommended, get_tech_stats
from ai_generator import add_ai_content
from storage import save_all
from notifier import send_deadline_alert

load_dotenv()


def load_config(path: str = "config.json") -> dict:
    if not os.path.exists(path):
        print(f"[오류] 설정 파일 '{path}'를 찾을 수 없습니다.")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def print_summary(jobs: list[dict], recommended: list[dict],
                  deadline_soon: list[dict]) -> None:
    sep = "=" * 60
    print(f"\n{sep}")
    print(" 취업 정보 자동화 - 분석 결과 요약")
    print(sep)
    print(f"  전체 수집 공고    : {len(jobs):>4}개")
    print(f"  마감 임박 공고    : {len(deadline_soon):>4}개 (3일 이내)")
    print(f"  추천 공고         : {len(recommended):>4}개")
    print(sep)

    if recommended:
        print("\n  [추천 공고 TOP 5]")
        for i, job in enumerate(recommended[:5], 1):
            print(f"  {i}. [{job.get('score',0):5.1f}점] {job.get('company',''):20s} "
                  f"| {job.get('title','')[:30]:30s} | {job.get('dday','')}")

    if deadline_soon:
        print("\n  [마감 임박 공고]")
        for job in deadline_soon:
            print(f"  >> {job.get('deadline','')} ({job.get('dday','')}) "
                  f"| {job.get('company',''):15s} | {job.get('title','')[:35]}")

    print(sep)


def main() -> None:
    print("=" * 60)
    print(" 취업 정보 자동화 시스템 시작")
    print("=" * 60)

    # 1. 설정 로드
    config = load_config("config.json")
    tech_stack = ", ".join(config["search"].get("tech_stack", []))
    print(f"\n[설정] 기술 스택: {tech_stack} | "
          f"지역: {config['search'].get('region','')} | "
          f"경력: {config['search'].get('experience','')}")

    # 2. 채용 공고 수집
    raw_jobs = collect_all_jobs(config)
    if not raw_jobs:
        print("[종료] 수집된 공고가 없습니다.")
        return

    # 3. 데이터 파싱 및 정제
    print("\n[정제] 데이터 파싱 및 중복 제거 중...")
    jobs = parse_and_clean(raw_jobs)
    jobs = filter_expired(jobs)  # 마감된 공고 제거
    jobs = filter_by_user_tech(jobs, config)

    # 4. 적합도 점수화
    print("[분석] 적합도 점수 계산 중...")
    jobs = score_jobs(jobs, config)

    # 5. 분류
    deadline_days = config.get("alert", {}).get("deadline_days", 3)
    deadline_soon = filter_deadline_soon(jobs, days=deadline_days)
    recommended = get_recommended(jobs, top_n=10)
    tech_stats = get_tech_stats(jobs)

    # 6. 자소서 포인트 및 면접 질문 생성 (추천 공고 기준)
    print("[생성] 자기소개서 포인트·면접 질문 생성 중...")
    recommended = add_ai_content(recommended)

    # 7. 결과 저장
    print("[저장] 결과 저장 중...")
    save_all(jobs, recommended, deadline_soon, tech_stats, config)

    # 8. 요약 출력
    print_summary(jobs, recommended, deadline_soon)

    # 9. 이메일 알림
    alert_enabled = config.get("alert", {}).get("enabled", False)
    if alert_enabled:
        print("\n[알림] 이메일 발송 중...")
        send_deadline_alert(
            deadline_soon=deadline_soon,
            recommended=recommended,
            excel_path=config["output"]["excel_path"],
        )
    else:
        print("\n[알림] 이메일 알림 비활성화 상태 (config.json의 alert.enabled 확인)")

    print("\n[완료] 모든 작업이 완료되었습니다.")


if __name__ == "__main__":
    main()
