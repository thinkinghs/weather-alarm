"""에어코리아 API 클라이언트 단위 테스트."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from src.air_quality import (
    AirForecastData,
    AirQualityData,
    _cai_grade,
    _parse_sido_grade,
    _pm10_grade,
    _pm25_grade,
    _safe_int,
    fetch_air_forecast,
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
    def _api_response(self) -> dict:
        return {
            "response": {
                "header": {"resultCode": "00"},
                "body": {
                    "items": [
                        {
                            "stationName": "서현동",
                            "pm10Value": "35",
                            "pm25Value": "18",
                            "khaiValue": "65",
                            "dataTime": "2026-04-26 07:00",
                        },
                        {
                            "stationName": "다른측정소",
                            "pm10Value": "50",
                            "pm25Value": "25",
                            "khaiValue": "80",
                            "dataTime": "2026-04-26 07:00",
                        },
                    ]
                },
            }
        }

    @patch("src.air_quality.requests.get")
    def test_finds_correct_station(self, mock_get: MagicMock) -> None:
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
    def test_station_not_found_raises(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = self._api_response()
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        with self.assertRaises(ValueError, msg="Station not found"):
            fetch_air_quality("test_key", "경기", "없는측정소")

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
        """측정값이 '-' 또는 None인 경우 0으로 처리한다."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "response": {
                "header": {"resultCode": "00"},
                "body": {
                    "items": [
                        {
                            "stationName": "서현동",
                            "pm10Value": "-",
                            "pm25Value": None,
                            "khaiValue": "N/A",
                            "dataTime": "2026-04-26 07:00",
                        }
                    ]
                },
            }
        }
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        result = fetch_air_quality("test_key", "경기", "서현동")
        self.assertEqual(result.pm10, 0)
        self.assertEqual(result.pm25, 0)
        self.assertEqual(result.cai, 0)


class TestParseSidoGrade(unittest.TestCase):
    _GRADE_STR = "서울 : 보통,인천 : 좋음,경기 : 나쁨,강원 : 좋음"

    def test_finds_correct_sido(self) -> None:
        self.assertEqual(_parse_sido_grade(self._GRADE_STR, "경기"), "나쁨")

    def test_finds_seoul(self) -> None:
        self.assertEqual(_parse_sido_grade(self._GRADE_STR, "서울"), "보통")

    def test_missing_sido_returns_no_info(self) -> None:
        self.assertEqual(_parse_sido_grade(self._GRADE_STR, "제주"), "정보없음")

    def test_empty_string_returns_no_info(self) -> None:
        self.assertEqual(_parse_sido_grade("", "경기"), "정보없음")


class TestFetchAirForecast(unittest.TestCase):
    def _forecast_response(self, inform_code: str, grade: str) -> dict:
        return {
            "response": {
                "body": {
                    "items": [
                        {
                            "informCode": inform_code,
                            "informGrade": f"서울 : 보통,경기 : {grade},강원 : 좋음",
                            "dataTime": "2026-04-26 17시 발표",
                            "dataTerm": "오늘",
                        }
                    ]
                }
            }
        }

    @patch("src.air_quality.requests.get")
    def test_parses_pm10_and_pm25_grades(self, mock_get: MagicMock) -> None:
        from datetime import datetime, timedelta, timezone
        KST = timezone(timedelta(hours=9))

        def side_effect(*args, **kwargs):
            params = kwargs.get("params", {})
            code = params.get("InformCode", "PM10")
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            if code == "PM10":
                mock_resp.json.return_value = self._forecast_response("PM10", "나쁨")
            else:
                mock_resp.json.return_value = self._forecast_response("PM25", "보통")
            return mock_resp

        mock_get.side_effect = side_effect
        now = datetime(2026, 4, 26, 7, 0, tzinfo=KST)
        result = fetch_air_forecast("test_key", "경기", _now=now)

        self.assertIsInstance(result, AirForecastData)
        self.assertEqual(result.pm10_grade, "나쁨")
        self.assertEqual(result.pm25_grade, "보통")
        self.assertEqual(result.forecast_date, "2026-04-26")

    @patch("src.air_quality.requests.get")
    def test_returns_no_info_on_api_failure(self, mock_get: MagicMock) -> None:
        from datetime import datetime, timedelta, timezone
        KST = timezone(timedelta(hours=9))
        mock_get.side_effect = ConnectionError("network error")

        now = datetime(2026, 4, 26, 7, 0, tzinfo=KST)
        result = fetch_air_forecast("test_key", "경기", _now=now)

        # 예보 실패 시 "정보없음"으로 처리 (예외 발생 안 함)
        self.assertEqual(result.pm10_grade, "정보없음")
        self.assertEqual(result.pm25_grade, "정보없음")


if __name__ == "__main__":
    unittest.main()
