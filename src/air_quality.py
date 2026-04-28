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
_SIDO_URL = (
    "http://apis.data.go.kr/B552584/ArpltnInforInqireSvc"
    "/getCtprvnRltmMesureDnsty"
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


def _fetch_station_items(api_key: str, station_name: str) -> list[dict]:
    """getMsrstnAcctoRltmMesureDnsty로 특정 측정소의 최근 24시간 데이터를 반환한다."""
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


def _find_valid_pm25(items: list[dict]) -> str | None:
    """측정 데이터 목록에서 유효한 첫 번째 PM2.5 값을 반환한다."""
    for item in items:
        v = item.get("pm25Value", "")
        if v and v.strip() != "-":
            return v
    return None


def _fetch_pm25_from_any_sido_station(
    api_key: str, sido_name: str, exclude_station: str
) -> str | None:
    """시도 내 임의 측정소 하나를 골라 PM2.5를 한 번 더 조회한다.

    getCtprvnRltmMesureDnsty로 시도 측정소 목록을 가져온 뒤,
    주 측정소가 아닌 곳 중 첫 번째를 getMsrstnAcctoRltmMesureDnsty로 재조회한다.
    """
    try:
        # 시도 내 측정소 목록 확인 (PM10/CAI 포함, stationName 식별용)
        body = _call_with_retry(_SIDO_URL, {
            "serviceKey": api_key,
            "returnType": "json",
            "numOfRows": 20,
            "pageNo": 1,
            "sidoName": sido_name,
            "searchCondition": "HOUR",
        })
        if body.get("response", {}).get("header", {}).get("resultCode") != "00":
            return None
        sido_items = body.get("response", {}).get("body", {}).get("items") or []

        # 주 측정소 제외하고 다른 측정소 선택
        fallback_station = next(
            (item.get("stationName") for item in sido_items
             if item.get("stationName") and item.get("stationName") != exclude_station),
            None,
        )
        if not fallback_station:
            return None

        # 해당 측정소의 PM2.5 조회
        logger.info("PM2.5 fallback: trying station=%s", fallback_station)
        fallback_items = _fetch_station_items(api_key, fallback_station)
        pm25_raw = _find_valid_pm25(fallback_items)
        if pm25_raw:
            logger.info("PM2.5 fallback: station=%s value=%s", fallback_station, pm25_raw)
        return pm25_raw

    except Exception as exc:
        logger.warning("PM2.5 fallback failed: %s", exc)
        return None


def fetch_air_quality(
    api_key: str,
    sido_name: str,
    station_name: str,
) -> AirQualityData:
    """에어코리아 측정소별 실시간 측정정보 API에서 특정 측정소 데이터를 조회한다.

    PM2.5가 24시간 내 없으면 시도 내 다른 측정소로 한 번 더 조회한다.
    그래도 없으면 측정없음으로 처리한다.
    """
    items = _fetch_station_items(api_key, station_name)
    station_data = items[0]

    pm25_raw = _find_valid_pm25(items)

    # PM2.5 없으면 시도 내 다른 측정소로 한 번 더 시도
    if pm25_raw is None and sido_name:
        pm25_raw = _fetch_pm25_from_any_sido_station(api_key, sido_name, station_name)

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
