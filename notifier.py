"""
notifier.py
마감 임박 공고 이메일 알림 모듈
- smtplib 기반 Gmail 발송
- 계정 정보는 .env 파일에서만 로드 (코드 내 직접 기입 금지)
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL", "")

# Gmail SMTP 서버 설정
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def send_deadline_alert(deadline_soon: list[dict], recommended: list[dict],
                        excel_path: str = "") -> bool:
    """
    마감 임박 공고 및 추천 공고를 이메일로 발송
    :param deadline_soon: 마감 임박 공고 목록
    :param recommended: 추천 공고 목록 (상위 5개)
    :param excel_path: 첨부할 Excel 파일 경로 (선택)
    :return: 발송 성공 여부
    """
    if not _check_email_config():
        return False

    if not deadline_soon and not recommended:
        print("[알림] 발송할 공고가 없습니다.")
        return False

    subject = f"[취업 알림] 마감 임박 공고 {len(deadline_soon)}건 | {datetime.now().strftime('%Y-%m-%d')}"
    body_html = _build_html_body(deadline_soon, recommended)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = RECIPIENT_EMAIL
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    # Excel 파일 첨부 (경로가 있고 파일이 존재할 때)
    if excel_path and os.path.exists(excel_path):
        with open(excel_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        filename = os.path.basename(excel_path)
        part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
        msg.attach(part)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, RECIPIENT_EMAIL, msg.as_string())
        print(f"[알림] 이메일 발송 완료 → {RECIPIENT_EMAIL}")
        return True
    except smtplib.SMTPAuthenticationError:
        print("[오류] 이메일 인증 실패. Gmail 앱 비밀번호를 확인하세요.")
        print("       Google 계정 → 보안 → 2단계 인증 → 앱 비밀번호 생성")
    except smtplib.SMTPException as e:
        print(f"[오류] 이메일 발송 실패: {e}")
    except Exception as e:
        print(f"[오류] 예기치 않은 오류: {e}")
    return False


def _build_html_body(deadline_soon: list[dict], recommended: list[dict]) -> str:
    """HTML 형식 이메일 본문 생성"""

    def job_row(job: dict, highlight: bool = False) -> str:
        bg = "#FFF3CD" if highlight else "#FFFFFF"
        return f"""
        <tr style="background-color:{bg};">
          <td style="padding:8px;border:1px solid #ddd;">{job.get('company','')}</td>
          <td style="padding:8px;border:1px solid #ddd;">
            <a href="{job.get('link','#')}" style="color:#0066CC;">{job.get('title','')}</a>
          </td>
          <td style="padding:8px;border:1px solid #ddd;">{job.get('location','')}</td>
          <td style="padding:8px;border:1px solid #ddd;color:#E74C3C;font-weight:bold;">
            {job.get('deadline','')} ({job.get('dday','')})
          </td>
          <td style="padding:8px;border:1px solid #ddd;">{job.get('score',0)}점</td>
        </tr>"""

    table_header = """
    <tr style="background-color:#1F4E79;color:white;">
      <th style="padding:10px;border:1px solid #ddd;">회사명</th>
      <th style="padding:10px;border:1px solid #ddd;">공고명</th>
      <th style="padding:10px;border:1px solid #ddd;">근무지</th>
      <th style="padding:10px;border:1px solid #ddd;">마감일</th>
      <th style="padding:10px;border:1px solid #ddd;">적합도</th>
    </tr>"""

    deadline_rows = "".join(job_row(j, highlight=True) for j in deadline_soon)
    rec_rows = "".join(job_row(j) for j in recommended[:5])

    now_str = datetime.now().strftime("%Y년 %m월 %d일 %H:%M")

    return f"""
    <html><body style="font-family:Arial,sans-serif;max-width:900px;margin:auto;">
      <h2 style="color:#1F4E79;">📋 취업 정보 자동화 — 채용 알림</h2>
      <p style="color:#555;">발송 시간: {now_str}</p>
      <hr style="border-color:#1F4E79;">

      <h3 style="color:#E74C3C;">⚠️ 마감 임박 공고 ({len(deadline_soon)}건)</h3>
      <table style="width:100%;border-collapse:collapse;">
        {table_header}{deadline_rows}
      </table>

      <br>
      <h3 style="color:#1F4E79;">⭐ 추천 공고 TOP 5</h3>
      <table style="width:100%;border-collapse:collapse;">
        {table_header}{rec_rows}
      </table>

      <br>
      <p style="color:#888;font-size:12px;">
        본 메일은 취업 정보 자동화 시스템에서 자동 발송되었습니다.<br>
        자세한 분석 결과는 첨부된 Excel 파일을 확인하세요.
      </p>
    </body></html>"""


def _check_email_config() -> bool:
    """이메일 설정 유효성 검사"""
    missing = []
    if not EMAIL_ADDRESS or EMAIL_ADDRESS == "발송에_사용할_Gmail_주소":
        missing.append("EMAIL_ADDRESS")
    if not EMAIL_PASSWORD or EMAIL_PASSWORD == "Gmail_앱_비밀번호_16자리":
        missing.append("EMAIL_PASSWORD")
    if not RECIPIENT_EMAIL or RECIPIENT_EMAIL == "알림_수신할_이메일_주소":
        missing.append("RECIPIENT_EMAIL")
    if missing:
        print(f"[경고] 이메일 설정 누락: {', '.join(missing)} - .env 파일을 확인하세요.")
        return False
    return True
