"""에어코리아 API 클라이언트 단위 테스트."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from src.air_quality import (
    AirQualityData,
    _cai_grade,
    _pm10_grade,
    _pm25_grade,
    _safe_int,
    fetch_air_quality,
)


class TestPm10Grade(unittest.TestCase):
    def test_good(self) -> None:
        self.assertEqual(_pm10_grade(0), "좋음")
        self.assertEqual(_pm10_grade(29), "좋음")

    def test_normal(self) -> None:
        self.assertEqual(_pm10_grade(30), "보통")
        self.assertEqual(_pm10_grade(79), "보통")

    def test_bad(self) -> None:
        self.assertEqual(_pm10_grade(80), "나쁨")
        self.assertEqual(_pm10_grade(149), "나쁨")

    def test_very_bad(self) -> None:
        self.assertEqual(_pm10_grade(150), "매우나쁨")
        self.assertEqual(_pm10_grade(300), "매우나쁨")


class TestPm25Grade(unittest.TestCase):
    def test_good(self) -> None:
        self.assertEqual(_pm25_grade(0), "좋음")
        self.assertEqual(_pm25_grade(14), "좋음")

    def test_normal(self) -> None:
        self.assertEqual(_pm25_grade(15), "보통")
        self.assertEqual(_pm25_grade(34), "보통")

    def test_bad(self) -> None:
        self.assertEqual(_pm25_grade(35), "나쁨")
        self.assertEqual(_pm25_grade(74), "나쁨")

    def test_very_bad(self) -> None:
        self.assertEqual(_pm25_grade(75), "매우나쁨")


class TestCaiGrade(unittest.TestCase):
    def test_good(self) -> None:
        self.assertEqual(_cai_grade(0), "좋음")
        self.assertEqual(_cai_grade(49), "좋음")

    def test_normal(self) -> None:
        self.assertEqual(_cai_grade(50), "보통")
        self.assertEqual(_cai_grade(99), "보통")

    def test_bad(self) -> None:
        self.assertEqual(_cai_grade(100), "나쁨")
        self.assertEqual(_cai_grade(249), "나쁨")

    def test_very_bad(self) -> None:
        self.assertEqual(_cai_grade(250), "매우나쁨")


class TestSafeInt(unittest.TestCase):
    def test_normal_string(self) -> None:
        self.assertEqual(_safe_int("35"), 35)

    def test_float_string(self) -> None:
        self.assertEqual(_safe_int("35.7"), 35)

    def test_none_returns_default(self) -> None:
        self.assertEqual(_safe_int(None), 0)
        self.assertEqual(_safe_int(None, default=99), 99)

    def test_invalid_string_returns_default(self) -> None:
        self.assertEqual(_safe_int("N/A"), 0)
        self.assertEqual(_safe_int("-"), 0)


def _station_resp(items: list[dict]) -> MagicMock:
    """getMsrstnAcctoRltmMesureDnsty 응답 mock."""
    m = MagicMock()
    m.json.return_value = {
        "response": {
            "header": {"resultCode": "00"},
            "body": {"items": items},
        }
    }
    m.raise_for_status.return_value = None
    return m


def _sido_resp(station_names: list[str]) -> MagicMock:
    """getCtprvnRltmMesureDnsty 응답 mock (stationName만 중요)."""
    m = MagicMock()
    m.json.return_value = {
        "response": {
            "header": {"resultCode": "00"},
            "body": {
                "items": [{"stationName": n, "pm10Value": "30"} for n in station_names]
            },
        }
    }
    m.raise_for_status.return_value = None
    return m


class TestFetchAirQuality(unittest.TestCase):

    @patch("src.air_quality.requests.get")
    def test_parses_most_recent_measurement(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _station_resp([
            {"stationName": "서현동", "pm10Value": "35", "pm25Value": "18",
             "khaiValue": "65", "dataTime": "2026-04-26 07:00"},
        ])

        result = fetch_air_quality("test_key", "경기", "서현동")

        self.assertIsInstance(result, AirQualityData)
        self.assertEqual(result.pm10, 35)
        self.assertEqual(result.pm10_grade, "보통")
        self.assertEqual(result.pm25, 18)
        self.assertEqual(result.pm25_grade, "보통")
        self.assertEqual(result.cai, 65)
        self.assertEqual(result.measured_at, "2026-04-26 07:00")

    @patch("src.air_quality.requests.get")
    def test_pm25_uses_most_recent_valid_value_in_24h(self, mock_get: MagicMock) -> None:
        """최신 측정이 '-'이면 24시간 이내 유효한 이전 값을 사용한다."""
        mock_get.return_value = _station_resp([
            {"stationName": "서현동", "pm10Value": "40", "pm25Value": "-",
             "khaiValue": "70", "dataTime": "2026-04-26 07:00"},
            {"stationName": "서현동", "pm10Value": "38", "pm25Value": "22",
             "khaiValue": "68", "dataTime": "2026-04-26 06:00"},
        ])

        result = fetch_air_quality("test_key", "경기", "서현동")

        self.assertEqual(result.pm10, 40)   # 최신 시간 pm10
        self.assertEqual(result.pm25, 22)   # 이전 시간 유효 pm25
        self.assertEqual(result.pm25_grade, "보통")

    @patch("src.air_quality.requests.get")
    def test_pm25_fallback_to_another_sido_station(self, mock_get: MagicMock) -> None:
        """24시간 내 PM2.5가 없으면 시도 내 다른 측정소로 한 번 더 시도한다."""
        # 1차: 주 측정소 (PM2.5 없음)
        primary = _station_resp([
            {"stationName": "정자동", "pm10Value": "30", "pm25Value": "-",
             "khaiValue": "60", "dataTime": "2026-04-26 07:00"},
        ])
        # 2차: 시도 목록
        sido = _sido_resp(["정자동", "판교동"])
        # 3차: 대체 측정소 (PM2.5 있음)
        fallback = _station_resp([
            {"stationName": "판교동", "pm10Value": "25", "pm25Value": "15",
             "khaiValue": "50", "dataTime": "2026-04-26 07:00"},
        ])
        mock_get.side_effect = [primary, sido, fallback]

        result = fetch_air_quality("test_key", "경기", "정자동")

        self.assertEqual(result.pm10, 30)   # 주 측정소 pm10
        self.assertEqual(result.pm25, 15)   # 대체 측정소 pm25
        self.assertEqual(result.pm25_grade, "보통")

    @patch("src.air_quality.requests.get")
    def test_pm25_shows_not_measured_when_all_fallbacks_fail(self, mock_get: MagicMock) -> None:
        """모든 fallback에서도 PM2.5가 없으면 측정없음으로 처리한다."""
        primary = _station_resp([
            {"stationName": "정자동", "pm10Value": "30", "pm25Value": "-",
             "khaiValue": "60", "dataTime": "2026-04-26 07:00"},
        ])
        sido = _sido_resp(["정자동", "판교동"])
        fallback = _station_resp([
            {"stationName": "판교동", "pm10Value": "25", "pm25Value": "-",
             "khaiValue": "50", "dataTime": "2026-04-26 07:00"},
        ])
        mock_get.side_effect = [primary, sido, fallback]

        result = fetch_air_quality("test_key", "경기", "정자동")

        self.assertIsNone(result.pm25)
        self.assertEqual(result.pm25_grade, "측정없음")

    @patch("src.air_quality.time.sleep")
    @patch("src.air_quality.requests.get")
    def test_retries_on_network_error(
        self, mock_get: MagicMock, mock_sleep: MagicMock
    ) -> None:
        mock_get.side_effect = ConnectionError("network error")

        with self.assertRaises(RuntimeError):
            fetch_air_quality("test_key", "경기", "서현동")

        self.assertEqual(mock_get.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("src.air_quality.requests.get")
    def test_handles_invalid_pm10_and_cai(self, mock_get: MagicMock) -> None:
        """pm10/cai가 '-'이면 0으로 처리한다."""
        mock_get.return_value = _station_resp([
            {"stationName": "서현동", "pm10Value": "-", "pm25Value": "10",
             "khaiValue": "N/A", "dataTime": "2026-04-26 07:00"},
        ])

        result = fetch_air_quality("test_key", "경기", "서현동")
        self.assertEqual(result.pm10, 0)
        self.assertEqual(result.pm25, 10)
        self.assertEqual(result.cai, 0)


if __name__ == "__main__":
    unittest.main()
