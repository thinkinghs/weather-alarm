"""기상청 API 클라이언트 단위 테스트."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from src.weather import (
    WeatherData,
    _fcst_value,
    _get_base_date,
    _get_base_time,
    fetch_weather,
)

KST = timezone(timedelta(hours=9))


def _kst(hour: int, minute: int = 0, day: int = 26) -> datetime:
    return datetime(2026, 4, day, hour, minute, tzinfo=KST)


class TestGetBaseTime(unittest.TestCase):
    def test_before_0210_returns_2300(self) -> None:
        self.assertEqual(_get_base_time(_kst(1, 0)), "2300")

    def test_at_0209_returns_2300(self) -> None:
        self.assertEqual(_get_base_time(_kst(2, 9)), "2300")

    def test_at_0210_returns_0200(self) -> None:
        self.assertEqual(_get_base_time(_kst(2, 10)), "0200")

    def test_at_0700_returns_0500(self) -> None:
        self.assertEqual(_get_base_time(_kst(7, 0)), "0500")

    def test_at_0810_returns_0800(self) -> None:
        self.assertEqual(_get_base_time(_kst(8, 15)), "0800")

    def test_at_2359_returns_2300(self) -> None:
        self.assertEqual(_get_base_time(_kst(23, 59)), "2300")

    def test_at_1110_returns_1100(self) -> None:
        self.assertEqual(_get_base_time(_kst(11, 10)), "1100")


class TestGetBaseDate(unittest.TestCase):
    def test_normal_time_returns_today(self) -> None:
        now = _kst(7, 0)
        self.assertEqual(_get_base_date(now, "0500"), "20260426")

    def test_2300_before_0300_returns_yesterday(self) -> None:
        now = _kst(1, 0)
        self.assertEqual(_get_base_date(now, "2300"), "20260425")

    def test_2300_at_0300_returns_today(self) -> None:
        now = _kst(3, 0)
        self.assertEqual(_get_base_date(now, "2300"), "20260426")

    def test_2300_after_0300_returns_today(self) -> None:
        now = _kst(10, 0)
        self.assertEqual(_get_base_date(now, "2300"), "20260426")


class TestFcstValue(unittest.TestCase):
    def _items(self) -> list[dict[str, str]]:
        return [
            {"category": "TMP", "fcstTime": "0600", "fcstValue": "12"},
            {"category": "TMP", "fcstTime": "0700", "fcstValue": "14"},
            {"category": "TMX", "fcstTime": "1500", "fcstValue": "22"},
        ]

    def test_exact_time_match(self) -> None:
        self.assertEqual(_fcst_value(self._items(), "TMP", "0700"), "14")

    def test_fallback_to_first_when_time_not_found(self) -> None:
        self.assertEqual(_fcst_value(self._items(), "TMP", "0900"), "12")

    def test_no_prefer_time_returns_first(self) -> None:
        self.assertEqual(_fcst_value(self._items(), "TMX"), "22")

    def test_missing_category_returns_none(self) -> None:
        self.assertIsNone(_fcst_value(self._items(), "WSD"))

    def test_empty_items(self) -> None:
        self.assertIsNone(_fcst_value([], "TMP"))


class TestFetchWeather(unittest.TestCase):
    def _api_response(self) -> dict:
        items = [
            {"fcstDate": "20260426", "fcstTime": "0700", "category": "TMP",  "fcstValue": "18"},
            {"fcstDate": "20260426", "fcstTime": "0600", "category": "TMN",  "fcstValue": "12"},
            {"fcstDate": "20260426", "fcstTime": "1500", "category": "TMX",  "fcstValue": "23"},
            {"fcstDate": "20260426", "fcstTime": "0700", "category": "SKY",  "fcstValue": "3"},
            {"fcstDate": "20260426", "fcstTime": "0700", "category": "PTY",  "fcstValue": "0"},
            {"fcstDate": "20260426", "fcstTime": "0600", "category": "POP",  "fcstValue": "10"},
            {"fcstDate": "20260426", "fcstTime": "0700", "category": "POP",  "fcstValue": "20"},
            {"fcstDate": "20260426", "fcstTime": "1200", "category": "POP",  "fcstValue": "40"},
            {"fcstDate": "20260426", "fcstTime": "1500", "category": "POP",  "fcstValue": "60"},
            {"fcstDate": "20260426", "fcstTime": "1800", "category": "POP",  "fcstValue": "50"},
            {"fcstDate": "20260426", "fcstTime": "0700", "category": "WSD",  "fcstValue": "3.2"},
            {"fcstDate": "20260426", "fcstTime": "0700", "category": "REH",  "fcstValue": "55"},
        ]
        return {
            "response": {
                "header": {"resultCode": "00", "resultMsg": "NORMAL_SERVICE"},
                "body": {"items": {"item": items}},
            }
        }

    @patch("src.weather.requests.get")
    def test_parses_response_correctly(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = self._api_response()
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        now = _kst(7, 0)
        result = fetch_weather("test_key", 61, 120, _now=now)

        self.assertIsInstance(result, WeatherData)
        self.assertEqual(result.current_temp, 18.0)
        self.assertEqual(result.min_temp, 12.0)
        self.assertEqual(result.max_temp, 23.0)
        self.assertEqual(result.sky_code, "3")
        self.assertEqual(result.pty_code, "0")
        self.assertEqual(result.precipitation_prob, 60)   # max of all POPs
        self.assertEqual(result.afternoon_precipitation_prob, 60)  # max of 1200/1500/1800
        self.assertAlmostEqual(result.wind_speed, 3.2)
        self.assertEqual(result.humidity, 55)
        self.assertEqual(result.forecast_date, "20260426")

    @patch("src.weather.requests.get")
    def test_api_error_code_raises(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "response": {
                "header": {"resultCode": "99", "resultMsg": "ERROR"},
                "body": {},
            }
        }
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        with self.assertRaises(RuntimeError):
            fetch_weather("bad_key", 61, 120, _now=_kst(7, 0))

    @patch("src.weather.requests.get")
    def test_tmn_tmx_fallback_to_tmp_minmax(self, mock_get: MagicMock) -> None:
        """TMN/TMX가 없으면 TMP 최솟/최댓값으로 대체한다."""
        items = [
            {"fcstDate": "20260426", "fcstTime": "0700", "category": "TMP",  "fcstValue": "18"},
            {"fcstDate": "20260426", "fcstTime": "0900", "category": "TMP",  "fcstValue": "21"},
            {"fcstDate": "20260426", "fcstTime": "1200", "category": "TMP",  "fcstValue": "24"},
            {"fcstDate": "20260426", "fcstTime": "1500", "category": "TMP",  "fcstValue": "25"},
            {"fcstDate": "20260426", "fcstTime": "1800", "category": "TMP",  "fcstValue": "20"},
            # TMN/TMX 없음
            {"fcstDate": "20260426", "fcstTime": "0700", "category": "SKY",  "fcstValue": "1"},
            {"fcstDate": "20260426", "fcstTime": "0700", "category": "PTY",  "fcstValue": "0"},
            {"fcstDate": "20260426", "fcstTime": "0700", "category": "POP",  "fcstValue": "10"},
            {"fcstDate": "20260426", "fcstTime": "0700", "category": "WSD",  "fcstValue": "2.0"},
            {"fcstDate": "20260426", "fcstTime": "0700", "category": "REH",  "fcstValue": "60"},
        ]
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "response": {
                "header": {"resultCode": "00", "resultMsg": "NORMAL_SERVICE"},
                "body": {"items": {"item": items}},
            }
        }
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        result = fetch_weather("test_key", 61, 120, _now=_kst(7, 0))

        self.assertEqual(result.min_temp, 18.0)  # TMP 최솟값
        self.assertEqual(result.max_temp, 25.0)  # TMP 최댓값

    @patch("src.weather.time.sleep")
    @patch("src.weather.requests.get")
    def test_retries_on_network_error(
        self, mock_get: MagicMock, mock_sleep: MagicMock
    ) -> None:
        mock_get.side_effect = ConnectionError("network error")

        with self.assertRaises(RuntimeError):
            fetch_weather("test_key", 61, 120, _now=_kst(7, 0))

        self.assertEqual(mock_get.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)  # 재시도 사이 sleep 2회


if __name__ == "__main__":
    unittest.main()
