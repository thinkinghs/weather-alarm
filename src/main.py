"""Morning weather & air quality briefing — 진입점."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# 로컬 개발 환경에서 .env 파일을 자동으로 로드 (python-dotenv 미설치 시 무시)
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

from .air_quality import fetch_air_forecast, fetch_air_quality
from .config import SensitiveFilter, load_config
from .formatter import format_error_message, format_message
from .line_messenger import send_message
from .weather import fetch_weather

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


def _install_sensitive_filter(secrets: list[str]) -> None:
    """루트 로거에 시크릿 마스킹 필터를 설치한다."""
    filt = SensitiveFilter(secrets)
    logging.getLogger().addFilter(filt)


def run() -> None:
    """날씨·공기질 데이터를 조회하고 LINE으로 메시지를 발송한다."""
    config = load_config()

    # 시크릿 마스킹 필터를 설치하여 이후 모든 로그에 적용
    _install_sensitive_filter([
        config.kma_api_key,
        config.airkorea_api_key,
        config.line_channel_access_token,
        *config.line_user_ids,
    ])

    errors: list[str] = []

    weather = None
    try:
        weather = fetch_weather(
            config.kma_api_key, config.location_nx, config.location_ny
        )
    except Exception:
        logger.exception("날씨 데이터 조회 실패")
        errors.append("날씨 정보 조회 실패")

    air_am = None
    try:
        air_am = fetch_air_quality(
            config.airkorea_api_key, config.sido_name, config.station_name
        )
    except Exception:
        logger.exception("공기질 데이터 조회 실패")
        errors.append("공기질 정보 조회 실패")

    # 오후 예보는 실패해도 메시지 발송은 계속 진행
    air_pm = None
    try:
        air_pm = fetch_air_forecast(config.airkorea_api_key, config.sido_name)
    except Exception:
        logger.warning("오후 공기질 예보 조회 실패 — 오후 섹션 생략")

    if errors or weather is None or air_am is None:
        error_text = format_error_message("\n".join(errors) if errors else "알 수 없는 오류")
        send_message(config.line_channel_access_token, config.line_user_ids, error_text)
        sys.exit(1)

    message = format_message(weather, air_am, air_pm, config.location_display_name)
    success = send_message(config.line_channel_access_token, config.line_user_ids, message)

    if not success:
        logger.error("LINE 메시지 발송 실패")
        sys.exit(1)

    logger.info("일일 브리핑 발송 완료")


if __name__ == "__main__":
    run()
