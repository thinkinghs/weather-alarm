"""LINE 메시지 포맷터."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .air_quality import AirQualityData
from .weather import WeatherData

KST = timezone(timedelta(hours=9))

_DAY_KO = ["월", "화", "수", "목", "금", "토", "일"]

_SKY_TEXT: dict[str, str] = {
    "1": "맑음",
    "3": "구름많음",
    "4": "흐림",
}
_SKY_EMOJI: dict[str, str] = {
    "1": "☀️",
    "3": "⛅",
    "4": "☁️",
}
_PTY_TEXT: dict[str, str] = {
    "0": "",
    "1": "비",
    "2": "비/눈",
    "3": "눈",
    "4": "소나기",
}
_PTY_EMOJI: dict[str, str] = {
    "1": "🌧",
    "2": "🌨",
    "3": "❄️",
    "4": "🌦",
}


def _sky_description(sky_code: str, pty_code: str) -> str:
    """강수 형태가 있으면 강수 형태를, 없으면 하늘 상태를 반환한다."""
    pty = _PTY_TEXT.get(pty_code, "")
    return pty if pty else _SKY_TEXT.get(sky_code, "맑음")


def _sky_emoji(sky_code: str, pty_code: str) -> str:
    """강수/하늘 상태에 맞는 이모지를 반환한다."""
    if pty_code in _PTY_EMOJI:
        return _PTY_EMOJI[pty_code]
    return _SKY_EMOJI.get(sky_code, "🌤")


def _air_realtime_section(label: str, data: AirQualityData) -> str:
    """실시간 측정값 공기질 섹션을 생성한다."""
    pm25_str = f"{data.pm25}㎍/㎥" if data.pm25 is not None else "-"
    return (
        f"{label}\n"
        f"😷 미세먼지(PM10): {data.pm10}㎍/㎥ ({data.pm10_grade})\n"
        f"💨 초미세먼지(PM2.5): {pm25_str} ({data.pm25_grade})\n"
        f"🌫 통합대기지수: {data.cai} ({data.cai_grade})"
    )


def format_message(
    weather: WeatherData,
    air_am: AirQualityData,
    location_name: str,
    _now: datetime | None = None,
) -> str:
    """날씨 및 공기질 데이터를 LINE 메시지 문자열로 변환한다."""
    now = _now if _now is not None else datetime.now(KST)
    date_str = now.strftime("%Y.%m.%d")
    day_str = _DAY_KO[now.weekday()]

    return (
        f"🌅 오늘의 날씨\n"
        f"📅 {date_str} ({day_str})\n"
        f"📍 {location_name}\n"
        f"\n"
        f"[날씨]\n"
        f"{_sky_emoji(weather.sky_code, weather.pty_code)} 하늘: "
        f"{_sky_description(weather.sky_code, weather.pty_code)}\n"
        f"🌡 기온: {weather.current_temp:.0f}°C "
        f"(최저 {weather.min_temp:.0f}°C / 최고 {weather.max_temp:.0f}°C)\n"
        f"💧 습도: {weather.humidity}%\n"
        f"🌬 바람: {weather.wind_speed:.1f}m/s\n"
        f"☔ 강수확률: {weather.precipitation_prob}% (오후 {weather.afternoon_precipitation_prob}%)\n"
        f"\n"
        f"[공기질]\n"
        f"{_air_realtime_section('오전', air_am)}"
    )


def format_error_message(context: str) -> str:
    """에러 알림 메시지를 생성한다. 민감 정보는 절대 포함하지 않는다."""
    now = datetime.now(KST)
    date_str = now.strftime("%Y.%m.%d %H:%M")
    return (
        f"⚠️ 날씨 알림 오류\n"
        f"📅 {date_str}\n\n"
        f"{context}\n\n"
        f"자세한 내용은 GitHub Actions 로그를 확인하세요."
    )
