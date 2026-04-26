"""한국환경공단 에어코리아 API 클라이언트.

- 실시간 측정정보: getCtprvnRltmMesureDnsty (오전 실측값)
- 대기질 예보:     getMinuDustFrcstDspth    (오후 예보 등급)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

_REALTIME_URL = (
    "http://apis.data.go.kr/B552584/ArpltnInforInqireSvc"
    "/getCtprvnRltmMesureDnsty"
)
_FORECAST_URL = (
    "http://apis.data.go.kr/B552584/ArpltnInforInqireSvc"
    "/getMinuDustFrcstDspth"
)
_TIMEOUT = 10
_MAX_RETRIES = 3


@dataclass
class AirQualityData:
    """실시간 측정 공기질 데이터."""
    pm10: int          # μg/m³
    pm10_grade: str    # 좋음 / 보통 / 나쁨 / 매우나쁨
    pm25: int          # μg/m³
    pm25_grade: str
    cai: int           # 통합대기환경지수
    cai_grade: str
    measured_at: str   # API가 반환하는 측정 시각 문자열


@dataclass
class AirForecastData:
    """에어코리아 예보 공기질 데이터 (등급만, 수치 없음)."""
    pm10_grade: str    # 좋음 / 보통 / 나쁨 / 매우나쁨 / 정보없음
    pm25_grade: str
    forecast_date: str  # YYYY-MM-DD


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


def _parse_sido_grade(inform_grade: str, sido_name: str) -> str:
    """informGrade 문자열에서 특정 시도의 등급을 추출한다.

    예: "서울 : 보통,경기 : 나쁨,강원 : 좋음" + "경기" → "나쁨"
    """
    for part in inform_grade.split(","):
        part = part.strip()
        if ":" in part:
            region, grade = part.split(":", 1)
            if region.strip() == sido_name:
                return grade.strip()
    return "정보없음"


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


def fetch_air_quality(
    api_key: str,
    sido_name: str,
    station_name: str,
) -> AirQualityData:
    """에어코리아 실시간 측정정보 API에서 특정 측정소 데이터를 조회한다."""
    body = _call_with_retry(_REALTIME_URL, {
        "serviceKey": api_key,
        "returnType": "json",
        "numOfRows": 100,
        "pageNo": 1,
        "sidoName": sido_name,
        "searchCondition": "HOUR",
    })
    items = body["response"]["body"]["items"]

    station_data = next(
        (item for item in items if item.get("stationName") == station_name),
        None,
    )
    if station_data is None:
        available = [item.get("stationName", "") for item in items]
        raise ValueError(
            f"Station '{station_name}' not found in '{sido_name}' response. "
            f"Available stations: {available}"
        )

    pm10 = _safe_int(station_data.get("pm10Value"))
    pm25 = _safe_int(station_data.get("pm25Value"))
    cai = _safe_int(station_data.get("khaiValue"))

    logger.info("Air quality fetched: station=%s", station_name)

    return AirQualityData(
        pm10=pm10,
        pm10_grade=_pm10_grade(pm10),
        pm25=pm25,
        pm25_grade=_pm25_grade(pm25),
        cai=cai,
        cai_grade=_cai_grade(cai),
        measured_at=station_data.get("dataTime", ""),
    )


def fetch_air_forecast(
    api_key: str,
    sido_name: str,
    _now: datetime | None = None,
) -> AirForecastData:
    """에어코리아 예보 API에서 오늘의 PM10/PM25 예보 등급을 조회한다.

    Args:
        api_key: 에어코리아 API 키.
        sido_name: 시도명 (예: "경기").
        _now: 테스트용 현재 시각 주입.
    """
    now = _now if _now is not None else datetime.now(KST)
    search_date = now.strftime("%Y-%m-%d")

    pm10_grade = "정보없음"
    pm25_grade = "정보없음"

    for inform_code, target in (("PM10", "pm10_grade"), ("PM25", "pm25_grade")):
        try:
            body = _call_with_retry(_FORECAST_URL, {
                "serviceKey": api_key,
                "returnType": "json",
                "numOfRows": 10,
                "pageNo": 1,
                "searchDate": search_date,
                "InformCode": inform_code,
            })
            items = body["response"]["body"]["items"]
            # 가장 최근 발표 기준 오늘 예보 사용
            today_items = [
                i for i in items
                if i.get("informCode") == inform_code
            ]
            if today_items:
                grade = _parse_sido_grade(
                    today_items[0].get("informGrade", ""), sido_name
                )
                if target == "pm10_grade":
                    pm10_grade = grade
                else:
                    pm25_grade = grade
        except Exception:
            logger.warning("Air forecast fetch failed for %s", inform_code)

    logger.info(
        "Air forecast fetched: sido=%s PM10=%s PM25=%s",
        sido_name, pm10_grade, pm25_grade,
    )

    return AirForecastData(
        pm10_grade=pm10_grade,
        pm25_grade=pm25_grade,
        forecast_date=search_date,
    )
