"""
scheduler.py
채용 공고 자동 수집 스케줄러 (APScheduler 기반)

실행 방법:
    python scheduler.py

스케줄:
    - 매일 08:00  — 공고 수집 + 저장 + 이메일 알림
    - 매일 18:00  — 마감 임박 공고 재확인 알림
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

import json
import os
import logging
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# 로그 설정 (파일 + 콘솔)
os.makedirs("output", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("output/scheduler.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def load_config(path: str = "config.json") -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run_collection(send_alert: bool = True) -> None:
    """공고 수집 전체 파이프라인 실행"""
    from api_collector import collect_all_jobs
    from data_parser  import parse_and_clean, filter_expired, filter_deadline_soon
    from analyzer     import score_jobs, get_recommended, get_tech_stats
    from ai_generator import add_ai_content
    from storage      import save_all
    from notifier     import send_deadline_alert

    logger.info("=" * 50)
    logger.info(f"자동 수집 시작: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    try:
        config = load_config()

        raw_jobs = collect_all_jobs(config)
        if not raw_jobs:
            logger.warning("수집된 공고 없음 — 종료")
            return

        jobs          = parse_and_clean(raw_jobs)
        jobs          = filter_expired(jobs)
        jobs          = score_jobs(jobs, config)
        deadline_days = config.get("alert", {}).get("deadline_days", 3)
        deadline_soon = filter_deadline_soon(jobs, days=deadline_days)
        recommended   = get_recommended(jobs, top_n=10)
        tech_stats    = get_tech_stats(jobs)
        recommended   = add_ai_content(recommended)

        save_all(jobs, recommended, deadline_soon, tech_stats, config)

        logger.info(
            f"완료 — 전체 {len(jobs)}개 | 추천 {len(recommended)}개 | "
            f"마감임박 {len(deadline_soon)}개"
        )

        # 이메일 알림 (config + send_alert 플래그 모두 True 일 때)
        alert_enabled = config.get("alert", {}).get("enabled", False)
        if send_alert and alert_enabled and (deadline_soon or recommended):
            send_deadline_alert(
                deadline_soon=deadline_soon,
                recommended=recommended,
                excel_path=config["output"]["excel_path"],
            )

    except FileNotFoundError:
        logger.error("config.json을 찾을 수 없습니다.")
    except Exception as e:
        logger.error(f"수집 중 오류 발생: {e}", exc_info=True)


def run_evening_alert() -> None:
    """저녁 마감 임박 공고 재알림 (저장 없이 알림만)"""
    from data_parser import filter_deadline_soon
    from storage     import save_sqlite
    from notifier    import send_deadline_alert
    import sqlite3

    logger.info("저녁 마감 임박 알림 확인 중...")
    try:
        config = load_config()
        db_path = config["output"]["db_path"]
        if not os.path.exists(db_path):
            logger.info("DB 없음 — 저녁 알림 건너뜀")
            return

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM jobs WHERE dday_num BETWEEN 0 AND 3"
        ).fetchall()
        conn.close()

        deadline_soon = [dict(r) for r in rows]
        if not deadline_soon:
            logger.info("마감 임박 공고 없음")
            return

        alert_enabled = config.get("alert", {}).get("enabled", False)
        if alert_enabled:
            send_deadline_alert(
                deadline_soon=deadline_soon,
                recommended=[],
                excel_path=config["output"]["excel_path"],
            )
            logger.info(f"저녁 알림 발송 완료: {len(deadline_soon)}건")
    except Exception as e:
        logger.error(f"저녁 알림 오류: {e}", exc_info=True)


def main() -> None:
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron       import CronTrigger
    except ImportError:
        print("[오류] APScheduler 미설치. pip install APScheduler")
        sys.exit(1)

    scheduler = BlockingScheduler(timezone="Asia/Seoul")

    # 매일 오전 8시 — 전체 수집 + 알림
    scheduler.add_job(
        run_collection,
        CronTrigger(hour=8, minute=0),
        id="morning_collection",
        name="오전 채용공고 수집",
        misfire_grace_time=3600,
        kwargs={"send_alert": True},
    )

    # 매일 오후 6시 — 마감 임박 재알림
    scheduler.add_job(
        run_evening_alert,
        CronTrigger(hour=18, minute=0),
        id="evening_alert",
        name="저녁 마감 임박 알림",
        misfire_grace_time=1800,
    )

    logger.info("스케줄러 시작 — 매일 08:00 수집, 18:00 마감 알림")
    logger.info("종료하려면 Ctrl+C 를 누르세요.")

    try:
        # 시작 시 즉시 1회 실행
        logger.info("초기 실행: 지금 바로 공고 수집합니다.")
        run_collection(send_alert=False)
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("스케줄러 종료")


if __name__ == "__main__":
    main()
