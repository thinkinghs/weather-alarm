"""한국환경공단 에어코리아 API 클라이언트.

- 실시간 측정정보: getMsrstnAcctoRltmMesureDnsty (측정소별 최근 24시간)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

_STATION_URL = (
    "http://apis.data.go.kr/B552584/ArpltnInforInqireSvc"
    "/getMsrstnAcctoRltmMesureDnsty"
)
_TIMEOUT = 10
_MAX_RETRIES = 3
_EMPTY_RETRY_WAIT = 300  # 빈 데이터 재시도 간격(초) — 아침 업데이트 대기용
_EMPTY_MAX_RETRIES = 3  # 빈 데이터 최대 재시도 횟수


@dataclass
class AirQualityData:
    """실시간 측정 공기질 데이터."""
    pm10: int           # μg/m³
    pm10_grade: str     # 좋음 / 보통 / 나쁨 / 매우나쁨
    pm25: int | None    # μg/m³, 측정값 없음("-" 반환) 시 None
    pm25_grade: str     # 좋음 / 보통 / 나쁨 / 매우나쁨 / 측정없음
    cai: int            # 통합대기환경지수
    cai_grade: str
    measured_at: str    # API가 반환하는 측정 시각 문자열


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


def _parse_optional_int(value: str | None) -> int | None:
    """공기질 측정값을 파싱한다. '-' 또는 빈 값은 None을 반환한다."""
    if not value or value.strip() == "-":
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def _call_with_retry(url: str, params: dict) -> dict:
    """API 호출 + exponential backoff 재시도."""
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, timeout=_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES - 1:
                delay = 2**attempt
                logger.warning(
                    "API attempt %d failed, retrying in %ds", attempt + 1, delay
                )
                time.sleep(delay)
    raise RuntimeError(
        f"API unavailable after {_MAX_RETRIES} attempts"
    ) from last_exc


def _fetch_items(api_key: str, station_name: str) -> list[dict]:
    """에어코리아 측정소별 API를 호출해 최근 24시간 items 목록을 반환한다."""
    params = {
        "serviceKey": api_key,
        "returnType": "json",
        "numOfRows": 24,
        "pageNo": 1,
        "stationName": station_name,
        "dataTerm": "DAILY",
    }
    for attempt in range(_EMPTY_MAX_RETRIES):
        body = _call_with_retry(_STATION_URL, params)

        header = body.get("response", {}).get("header", {})
        result_code = header.get("resultCode", "")
        if result_code != "00":
            raise RuntimeError(
                f"AirKorea API error: resultCode={result_code}, "
                f"resultMsg={header.get('resultMsg', '')}"
            )

        items = body.get("response", {}).get("body", {}).get("items")
        # 단일 결과는 dict로 반환될 수 있으므로 list로 정규화
        if isinstance(items, dict):
            items = [items]
        if items:
            return items

        if attempt < _EMPTY_MAX_RETRIES - 1:
            logger.warning(
                "AirKorea returned empty items (attempt %d/%d), "
                "retrying in %ds — 데이터 업데이트 대기 중",
                attempt + 1,
                _EMPTY_MAX_RETRIES,
                _EMPTY_RETRY_WAIT,
            )
            time.sleep(_EMPTY_RETRY_WAIT)

    raise RuntimeError(
        f"AirKorea API returned empty items after {_EMPTY_MAX_RETRIES} attempts "
        f"for station='{station_name}'"
    )


def fetch_air_quality(
    api_key: str,
    sido_name: str,
    station_name: str,
) -> AirQualityData:
    """에어코리아 측정소별 실시간 측정정보 API에서 특정 측정소 데이터를 조회한다.

    최근 24시간 데이터를 조회해 PM2.5 등 미갱신 항목은 가장 최근 유효값을 사용한다.
    sido_name은 에러 메시지용으로만 유지한다.
    """
    items = _fetch_items(api_key, station_name)

    # 가장 최근 측정값(인덱스 0)을 기본 데이터로 사용
    station_data = items[0]

    # PM2.5는 시간별로 누락("-")될 수 있으므로 최근 24시간에서 유효한 첫 번째 값을 사용
    pm25_raw: str | None = None
    for item in items:
        v = item.get("pm25Value", "")
        if v and v.strip() != "-":
            pm25_raw = v
            break

    pm10 = _safe_int(station_data.get("pm10Value"))
    pm25 = _parse_optional_int(pm25_raw)
    cai = _safe_int(station_data.get("khaiValue"))

    logger.info(
        "Air quality fetched: station=%s pm10=%d pm25=%s",
        station_name, pm10, pm25_raw or "-",
    )

    return AirQualityData(
        pm10=pm10,
        pm10_grade=_pm10_grade(pm10),
        pm25=pm25,
        pm25_grade=_pm25_grade(pm25) if pm25 is not None else "측정없음",
        cai=cai,
        cai_grade=_cai_grade(cai),
        measured_at=station_data.get("dataTime", ""),
    )


