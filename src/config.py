"""환경변수 로딩 및 검증 모듈."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass


def mask_secret(value: str, visible: int = 3) -> str:
    """민감한 값을 로그 출력용으로 마스킹한다."""
    if not value:
        return "***"
    if len(value) <= visible * 2:
        return "***"
    return f"{value[:visible]}***{value[-visible:]}"


class SensitiveFilter(logging.Filter):
    """지정된 시크릿 값을 로그 레코드에서 자동으로 마스킹하는 필터."""

    def __init__(self, secrets: list[str]) -> None:
        super().__init__()
        # 길이가 충분히 긴 값만 마스킹 대상으로 등록
        self._secrets = [s for s in secrets if s and len(s) > 6]

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._mask(str(record.msg))
        if isinstance(record.args, tuple):
            record.args = tuple(self._mask(str(a)) for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: self._mask(str(v)) for k, v in record.args.items()}
        return True

    def _mask(self, text: str) -> str:
        for secret in self._secrets:
            if secret in text:
                text = text.replace(secret, mask_secret(secret))
        return text


@dataclass(frozen=True)
class Config:
    kma_api_key: str
    airkorea_api_key: str
    line_channel_access_token: str
    line_user_id: str
    location_nx: int
    location_ny: int
    sido_name: str
    station_name: str
    location_display_name: str


def load_config() -> Config:
    """환경변수를 로드하고 필수 값이 모두 존재하는지 검증한다.

    Raises:
        ValueError: 필수 환경변수가 하나라도 누락된 경우.
    """
    required_keys = [
        "KMA_API_KEY",
        "AIRKOREA_API_KEY",
        "LINE_CHANNEL_ACCESS_TOKEN",
        "LINE_USER_ID",
    ]
    missing = [key for key in required_keys if not os.environ.get(key)]
    if missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}"
        )

    config = Config(
        kma_api_key=os.environ["KMA_API_KEY"],
        airkorea_api_key=os.environ["AIRKOREA_API_KEY"],
        line_channel_access_token=os.environ["LINE_CHANNEL_ACCESS_TOKEN"],
        line_user_id=os.environ["LINE_USER_ID"],
        location_nx=int(os.environ.get("LOCATION_NX", "61")),
        location_ny=int(os.environ.get("LOCATION_NY", "120")),
        sido_name=os.environ.get("SIDO_NAME", "경기"),
        station_name=os.environ.get("STATION_NAME", "서현동"),
        location_display_name=os.environ.get(
            "LOCATION_DISPLAY_NAME", "경기도 성남시 분당구"
        ),
    )

    logger = logging.getLogger(__name__)
    logger.info(
        "Config loaded — kma=%s airkorea=%s line_token=%s",
        mask_secret(config.kma_api_key),
        mask_secret(config.airkorea_api_key),
        mask_secret(config.line_channel_access_token),
    )
    return config
