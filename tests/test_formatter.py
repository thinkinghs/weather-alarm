"""포맷터 단위 테스트."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from src.air_quality import AirQualityData
from src.formatter import (
    _air_section,
    _sky_description,
    _sky_emoji,
    format_error_message,
    format_message,
)
from src.weather import WeatherData

KST = timezone(timedelta(hours=9))


def _sample_weather() -> WeatherData:
    return WeatherData(
        current_temp=18.0,
        min_temp=12.0,
        max_temp=23.0,
        sky_code="3",
        pty_code="0",
        precipitation_prob=20,
        wind_speed=3.2,
        humidity=55,
        forecast_date="20260426",
    )


def _sample_air() -> AirQualityData:
    return AirQualityData(
        pm10=35,
        pm10_grade="보통",
        pm25=18,
        pm25_grade="보통",
        cai=65,
        cai_grade="보통",
        measured_at="2026-04-26 07:00",
    )


class TestSkyDescription(unittest.TestCase):
    def test_clear_sky(self) -> None:
        self.assertEqual(_sky_description("1", "0"), "맑음")

    def test_cloudy(self) -> None:
        self.assertEqual(_sky_description("3", "0"), "구름많음")

    def test_overcast(self) -> None:
        self.assertEqual(_sky_description("4", "0"), "흐림")

    def test_rain_overrides_sky(self) -> None:
        self.assertEqual(_sky_description("1", "1"), "비")

    def test_snow(self) -> None:
        self.assertEqual(_sky_description("1", "3"), "눈")

    def test_shower(self) -> None:
        self.assertEqual(_sky_description("3", "4"), "소나기")


class TestSkyEmoji(unittest.TestCase):
    def test_clear(self) -> None:
        self.assertEqual(_sky_emoji("1", "0"), "☀️")

    def test_partly_cloudy(self) -> None:
        self.assertEqual(_sky_emoji("3", "0"), "⛅")

    def test_rain_emoji(self) -> None:
        self.assertEqual(_sky_emoji("1", "1"), "🌧")

    def test_snow_emoji(self) -> None:
        self.assertEqual(_sky_emoji("1", "3"), "❄️")


class TestAirSection(unittest.TestCase):
    def test_section_contains_label(self) -> None:
        section = _air_section("오전", _sample_air())
        self.assertTrue(section.startswith("오전"))

    def test_section_contains_pm10(self) -> None:
        section = _air_section("오전", _sample_air())
        self.assertIn("35㎍/㎥", section)
        self.assertIn("PM10", section)

    def test_section_contains_pm25(self) -> None:
        section = _air_section("오전", _sample_air())
        self.assertIn("18㎍/㎥", section)
        self.assertIn("PM2.5", section)

    def test_section_contains_cai(self) -> None:
        section = _air_section("오전", _sample_air())
        self.assertIn("65", section)
        self.assertIn("통합대기지수", section)

    def test_grade_text_included(self) -> None:
        section = _air_section("오전", _sample_air())
        self.assertIn("보통", section)


class TestFormatMessage(unittest.TestCase):
    def setUp(self) -> None:
        self._now = datetime(2026, 4, 26, 7, 0, tzinfo=KST)
        self._msg = format_message(
            _sample_weather(),
            _sample_air(),
            _sample_air(),
            "경기도 성남시 분당구",
            _now=self._now,
        )

    def test_contains_date(self) -> None:
        self.assertIn("2026.04.26", self._msg)

    def test_contains_day_of_week(self) -> None:
        self.assertIn("(일)", self._msg)

    def test_contains_location(self) -> None:
        self.assertIn("경기도 성남시 분당구", self._msg)

    def test_contains_temperature(self) -> None:
        self.assertIn("18°C", self._msg)
        self.assertIn("12°C", self._msg)
        self.assertIn("23°C", self._msg)

    def test_contains_humidity(self) -> None:
        self.assertIn("55%", self._msg)

    def test_contains_wind(self) -> None:
        self.assertIn("3.2m/s", self._msg)

    def test_contains_precipitation(self) -> None:
        self.assertIn("20%", self._msg)

    def test_contains_am_pm_labels(self) -> None:
        self.assertIn("오전", self._msg)
        self.assertIn("오후", self._msg)

    def test_contains_air_quality_section(self) -> None:
        self.assertIn("[공기질]", self._msg)

    def test_rain_day_uses_rain_description(self) -> None:
        weather = WeatherData(
            current_temp=15.0,
            min_temp=10.0,
            max_temp=18.0,
            sky_code="4",
            pty_code="1",
            precipitation_prob=80,
            wind_speed=2.0,
            humidity=80,
            forecast_date="20260426",
        )
        msg = format_message(
            weather, _sample_air(), _sample_air(), "서울", _now=self._now
        )
        self.assertIn("비", msg)


class TestFormatErrorMessage(unittest.TestCase):
    def test_contains_error_header(self) -> None:
        msg = format_error_message("날씨 정보 조회 실패")
        self.assertIn("⚠️", msg)
        self.assertIn("날씨 알림 오류", msg)

    def test_contains_context(self) -> None:
        msg = format_error_message("날씨 정보 조회 실패")
        self.assertIn("날씨 정보 조회 실패", msg)

    def test_no_sensitive_placeholders(self) -> None:
        """에러 메시지에 API 키나 토큰 관련 단어가 없어야 한다."""
        msg = format_error_message("조회 실패")
        self.assertNotIn("token", msg.lower())
        self.assertNotIn("api_key", msg.lower())
        self.assertNotIn("secret", msg.lower())


if __name__ == "__main__":
    unittest.main()
