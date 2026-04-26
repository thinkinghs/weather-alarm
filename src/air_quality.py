"""한국환경공단 에어코리아 시도별 실시간 측정정보 API 클라이언트."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

_AIRKOREA_URL = (
    "http://apis.data.go.kr/B552584/ArpltnInforInqireSvc"
    "/getCtprvnRltmMesureDnsty"
)
_TIMEOUT = 10       # seconds
_MAX_RETRIES = 3


@dataclass
class AirQualityData:
    pm10: int          # μg/m³
    pm10_grade: str    # 좋음 / 보통 / 나쁨 / 매우나쁨
    pm25: int          # μg/m³
    pm25_grade: str
    cai: int           # 통합대기환경지수
    cai_grade: str
    measured_at: str   # API가 반환하는 측정 시각 문자열


def _pm10_grade(value: int) -> str:
    if value < 30:
        return "좋음"
    if value < 80:
        return "보통"
    if value < 150:
        return "나쁨"
    return "매우나쁨"


def _pm25_grade(value: int) -> str:
    if value < 15:
        return "좋음"
    if value < 35:
        return "보통"
    if value < 75:
        return "나쁨"
    return "매우나쁨"


def _cai_grade(value: int) -> str:
    if value < 50:
        return "좋음"
    if value < 100:
        return "보통"
    if value < 250:
        return "나쁨"
    return "매우나쁨"


def _safe_int(value: str | None, default: int = 0) -> int:
    """문자열을 정수로 변환한다. 실패 시 default를 반환."""
    try:
        return int(float(value)) if value else default
    except (ValueError, TypeError):
        return default


def _call_api(api_key: str, sido_name: str) -> list[dict]:
    """에어코리아 API를 호출하며 실패 시 exponential backoff 재시도한다."""
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            resp = requests.get(
                _AIRKOREA_URL,
                params={
                    "serviceKey": api_key,
                    "returnType": "json",
                    "numOfRows": 100,
                    "pageNo": 1,
                    "sidoName": sido_name,
                    "searchCondition": "HOUR",
                },
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            body = resp.json()
            return body["response"]["body"]["items"]
        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES - 1:
                delay = 2**attempt
                logger.warning(
                    "AirKorea API attempt %d failed, retrying in %ds",
                    attempt + 1,
                    delay,
                )
                time.sleep(delay)
    raise RuntimeError(
        f"AirKorea API unavailable after {_MAX_RETRIES} attempts"
    ) from last_exc


def fetch_air_quality(
    api_key: str,
    sido_name: str,
    station_name: str,
) -> AirQualityData:
    """에어코리아 API에서 특정 측정소의 실시간 공기질 데이터를 조회한다.

    Args:
        api_key: 에어코리아 API 키.
        sido_name: 시도명 (예: "경기").
        station_name: 측정소명 (예: "서현동").

    Raises:
        ValueError: 해당 측정소 데이터를 찾을 수 없는 경우.
    """
    items = _call_api(api_key, sido_name)

    station_data = next(
        (item for item in items if item.get("stationName") == station_name),
        None,
    )
    if station_data is None:
        raise ValueError(
            f"Station '{station_name}' not found in '{sido_name}' response"
        )

    pm10 = _safe_int(station_data.get("pm10Value"))
    pm25 = _safe_int(station_data.get("pm25Value"))
    cai = _safe_int(station_data.get("khaiValue"))
    measured_at = station_data.get("dataTime", "")

    logger.info("Air quality fetched: station=%s", station_name)

    return AirQualityData(
        pm10=pm10,
        pm10_grade=_pm10_grade(pm10),
        pm25=pm25,
        pm25_grade=_pm25_grade(pm25),
        cai=cai,
        cai_grade=_cai_grade(cai),
        measured_at=measured_at,
    )
