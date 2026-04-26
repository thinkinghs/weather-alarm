"""LINE Messaging API Push Message 발송 클라이언트."""
from __future__ import annotations

import logging
import time

import requests

logger = logging.getLogger(__name__)

_LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
_TIMEOUT = 10       # seconds
_MAX_RETRIES = 3


def send_message(token: str, user_id: str, text: str) -> bool:
    """LINE Push Message를 발송한다.

    응답 바디를 로깅하지 않는다 (헤더에 토큰 정보가 포함될 수 있음).

    Args:
        token: LINE Channel Access Token.
        user_id: 수신자 LINE User ID.
        text: 발송할 메시지 본문.

    Returns:
        발송 성공 시 True, 실패 시 False.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "to": user_id,
        "messages": [{"type": "text", "text": text}],
    }

    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            resp = requests.post(
                _LINE_PUSH_URL,
                headers=headers,
                json=payload,
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            # status code만 로깅 (응답 바디 원문 로깅 금지)
            logger.info("LINE message sent (status=%d)", resp.status_code)
            return True
        except requests.HTTPError as exc:
            status = (
                exc.response.status_code if exc.response is not None else "unknown"
            )
            last_exc = exc
            logger.error(
                "LINE API HTTP error: status=%s attempt=%d", status, attempt + 1
            )
        except Exception as exc:
            last_exc = exc
            logger.error(
                "LINE API error: %s attempt=%d", type(exc).__name__, attempt + 1
            )

        if attempt < _MAX_RETRIES - 1:
            delay = 2**attempt
            logger.warning("Retrying LINE API in %ds", delay)
            time.sleep(delay)

    logger.error("LINE message failed after %d attempts", _MAX_RETRIES)
    return False
