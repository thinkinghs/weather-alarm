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


class TestFetchAirQuality(unittest.TestCase):
    def _api_response(self, items: list[dict] | None = None) -> dict:
        """getMsrstnAcctoRltmMesureDnsty 응답 형식 (측정소 1곳의 시간별 데이터)."""
        if items is None:
            items = [
                {
                    "stationName": "서현동",
                    "pm10Value": "35",
                    "pm25Value": "18",
                    "khaiValue": "65",
                    "dataTime": "2026-04-26 07:00",
                },
                {
                    "stationName": "서현동",
                    "pm10Value": "38",
                    "pm25Value": "20",
                    "khaiValue": "68",
                    "dataTime": "2026-04-26 06:00",
                },
            ]
        return {
            "response": {
                "header": {"resultCode": "00"},
                "body": {"items": items},
            }
        }

    @patch("src.air_quality.requests.get")
    def test_parses_most_recent_measurement(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = self._api_response()
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        result = fetch_air_quality("test_key", "경기", "서현동")

        self.assertIsInstance(result, AirQualityData)
        self.assertEqual(result.pm10, 35)
        self.assertEqual(result.pm10_grade, "보통")
        self.assertEqual(result.pm25, 18)
        self.assertEqual(result.pm25_grade, "보통")
        self.assertEqual(result.cai, 65)
        self.assertEqual(result.cai_grade, "보통")
        self.assertEqual(result.measured_at, "2026-04-26 07:00")

    @patch("src.air_quality.requests.get")
    def test_pm25_fallback_to_recent_valid_value(self, mock_get: MagicMock) -> None:
        """최신 시간 PM2.5가 '-'이면 이전 시간의 유효한 값을 사용한다."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = self._api_response(items=[
            {
                "stationName": "서현동",
                "pm10Value": "40",
                "pm25Value": "-",    # 최신 시간 PM2.5 누락
                "khaiValue": "70",
                "dataTime": "2026-04-26 07:00",
            },
            {
                "stationName": "서현동",
                "pm10Value": "38",
                "pm25Value": "22",   # 이전 시간에 유효한 PM2.5 존재
                "khaiValue": "68",
                "dataTime": "2026-04-26 06:00",
            },
        ])
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        result = fetch_air_quality("test_key", "경기", "서현동")

        # pm10/cai는 최신 시간값 사용
        self.assertEqual(result.pm10, 40)
        self.assertEqual(result.cai, 70)
        # pm25는 이전 시간 유효값으로 fallback
        self.assertEqual(result.pm25, 22)
        self.assertEqual(result.pm25_grade, "보통")

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
    def test_handles_invalid_measurement_values(self, mock_get: MagicMock) -> None:
        """측정값이 '-' 또는 None인 경우: pm10/cai는 0, pm25는 None으로 처리한다."""
        # 1차: 측정소별 API (pm25Value=None)
        # 2차: 시도별 API (pm25Value도 없음)
        station_resp = MagicMock()
        station_resp.json.return_value = self._api_response(items=[
            {
                "stationName": "서현동",
                "pm10Value": "-",
                "pm25Value": None,
                "khaiValue": "N/A",
                "dataTime": "2026-04-26 07:00",
            }
        ])
        station_resp.raise_for_status.return_value = None

        sido_resp = MagicMock()
        sido_resp.json.return_value = {
            "response": {
                "header": {"resultCode": "00"},
                "body": {
                    "items": [
                        {"stationName": "다른측정소", "pm25Value": "-"},
                    ]
                },
            }
        }
        sido_resp.raise_for_status.return_value = None

        mock_get.side_effect = [station_resp, sido_resp]

        result = fetch_air_quality("test_key", "경기", "서현동")
        self.assertEqual(result.pm10, 0)
        self.assertIsNone(result.pm25)
        self.assertEqual(result.pm25_grade, "측정없음")
        self.assertEqual(result.cai, 0)

    @patch("src.air_quality.requests.get")
    def test_pm25_sido_fallback_when_station_has_no_pm25(self, mock_get: MagicMock) -> None:
        """측정소 24시간 내 PM2.5가 없으면 시도 내 다른 측정소 값으로 fallback한다."""
        # 1차: 측정소별 API (pm25Value 없음)
        station_resp = MagicMock()
        station_resp.json.return_value = self._api_response(items=[
            {
                "stationName": "서현동",
                "pm10Value": "30",
                "pm25Value": "-",
                "khaiValue": "60",
                "dataTime": "2026-04-26 07:00",
            }
        ])
        station_resp.raise_for_status.return_value = None

        # 2차: 시도별 API (다른 측정소 PM2.5 유효값 존재)
        sido_resp = MagicMock()
        sido_resp.json.return_value = {
            "response": {
                "header": {"resultCode": "00"},
                "body": {
                    "items": [
                        {"stationName": "판교동", "pm25Value": "15"},
                    ]
                },
            }
        }
        sido_resp.raise_for_status.return_value = None

        mock_get.side_effect = [station_resp, sido_resp]

        result = fetch_air_quality("test_key", "경기", "서현동")
        self.assertEqual(result.pm10, 30)
        self.assertEqual(result.pm25, 15)
        self.assertEqual(result.pm25_grade, "보통")


if __name__ == "__main__":
    unittest.main()
