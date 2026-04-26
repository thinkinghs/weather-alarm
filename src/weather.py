"""기상청 단기예보 API 클라이언트."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

_KMA_URL = (
    "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
)
# 단기예보 발표 시각 (매 3시간, 실제 제공은 발표 후 약 10분 뒤)
_BASE_TIMES = ["0200", "0500", "0800", "1100", "1400", "1700", "2000", "2300"]
_TIMEOUT = 10       # seconds
_MAX_RETRIES = 3


@dataclass
class WeatherData:
    current_temp: float      # °C
    min_temp: float          # °C
    max_temp: float          # °C
    sky_code: str            # 1=맑음, 3=구름많음, 4=흐림
    pty_code: str            # 0=없음, 1=비, 2=비/눈, 3=눈, 4=소나기
    precipitation_prob: int  # %
    wind_speed: float        # m/s
    humidity: int            # %
    forecast_date: str       # YYYYMMDD


def _get_base_time(now: datetime) -> str:
    """현재 KST 시각 기준으로 가장 최근에 발표된 base_time을 반환한다.

    각 base_time은 발표 후 약 10분 뒤부터 API 조회가 가능하다.
    """
    current_hhmm = now.hour * 100 + now.minute
    available = [t for t in _BASE_TIMES if int(t) + 10 <= current_hhmm]
    return available[-1] if available else "2300"


def _get_base_date(now: datetime, base_time: str) -> str:
    """base_time이 전날 2300인 경우 날짜를 하루 앞으로 조정한다."""
    if base_time == "2300" and now.hour < 3:
        return (now - timedelta(days=1)).strftime("%Y%m%d")
    return now.strftime("%Y%m%d")


def _fcst_value(
    items: list[dict[str, str]],
    category: str,
    prefer_time: str | None = None,
) -> str | None:
    """카테고리와 선호 시각으로 예보값을 찾는다. 해당 시각이 없으면 첫 번째 값을 반환."""
    candidates = [i for i in items if i["category"] == category]
    if not candidates:
        return None
    if prefer_time:
        for item in candidates:
            if item["fcstTime"] == prefer_time:
                return item["fcstValue"]
    return candidates[0]["fcstValue"]


def _call_api(api_key: str, params: dict[str, Any]) -> dict[str, Any]:
    """KMA API를 호출하며 실패 시 exponential backoff 재시도한다."""
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            resp = requests.get(
                _KMA_URL,
                params={"serviceKey": api_key, **params},
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            body = resp.json()
            header = body["response"]["header"]
            if header["resultCode"] != "00":
                raise ValueError(f"KMA API error: {header['resultCode']}")
            return body
        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES - 1:
                delay = 2**attempt
                logger.warning(
                    "KMA API attempt %d failed, retrying in %ds", attempt + 1, delay
                )
                time.sleep(delay)
    raise RuntimeError(
        f"KMA API unavailable after {_MAX_RETRIES} attempts"
    ) from last_exc


def fetch_weather(
    api_key: str,
    nx: int,
    ny: int,
    _now: datetime | None = None,
) -> WeatherData:
    """기상청 단기예보 API에서 오늘의 날씨 데이터를 조회한다.

    Args:
        api_key: 기상청 공공데이터포털 API 키.
        nx: 기상청 격자 X 좌표.
        ny: 기상청 격자 Y 좌표.
        _now: 테스트용 현재 시각 주입 (None이면 실제 KST 현재 시각 사용).
    """
    now = _now if _now is not None else datetime.now(KST)
    base_time = _get_base_time(now)
    base_date = _get_base_date(now, base_time)
    today = now.strftime("%Y%m%d")
    hour_str = f"{now.hour:02d}00"

    data = _call_api(api_key, {
        "pageNo": 1,
        "numOfRows": 1000,
        "dataType": "JSON",
        "base_date": base_date,
        "base_time": base_time,
        "nx": nx,
        "ny": ny,
    })

    raw = data["response"]["body"]["items"]["item"]
    # 단일 결과는 dict로 반환되는 경우가 있어 list로 정규화
    items: list[dict[str, str]] = raw if isinstance(raw, list) else [raw]
    today_items = [i for i in items if i["fcstDate"] == today]

    logger.info(
        "Weather fetched: date=%s base_time=%s total_items=%d today_items=%d",
        today, base_time, len(items), len(today_items),
    )

    if not today_items:
        raise ValueError(
            f"No forecast items found for today={today} "
            f"(base_date={base_date}, base_time={base_time}). "
            f"Available dates: {sorted({i['fcstDate'] for i in items})}"
        )

    pops = [
        int(i["fcstValue"])
        for i in today_items
        if i["category"] == "POP" and i["fcstValue"].lstrip("-").isdigit()
    ]

    return WeatherData(
        current_temp=float(_fcst_value(today_items, "TMP", hour_str) or 0),
        min_temp=float(_fcst_value(today_items, "TMN") or 0),
        max_temp=float(_fcst_value(today_items, "TMX") or 0),
        sky_code=_fcst_value(today_items, "SKY", hour_str) or "1",
        pty_code=_fcst_value(today_items, "PTY", hour_str) or "0",
        precipitation_prob=max(pops) if pops else 0,
        wind_speed=float(_fcst_value(today_items, "WSD", hour_str) or 0),
        humidity=int(_fcst_value(today_items, "REH", hour_str) or 0),
        forecast_date=today,
    )
