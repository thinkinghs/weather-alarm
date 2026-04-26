# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Commands

```bash
# 로컬 개발 환경 설정
uv venv                   # 가상환경 생성 (.venv/)
uv sync                   # 모든 의존성 설치 (dev 포함)
cp .env.example .env      # 실제 API 키 입력 후 사용
uv run pre-commit install

# 앱 실행 (프로젝트 루트에서)
uv run python -m src.main

# 전체 테스트
uv run pytest tests/ -v

# 특정 테스트 파일
uv run pytest tests/test_formatter.py -v

# 특정 테스트 케이스
uv run pytest tests/test_weather.py::TestGetBaseTime::test_at_0700_returns_0500 -v

# 의존성 추가 (런타임)
uv add <package>

# 의존성 추가 (개발용)
uv add --dev <package>

# lock 파일 갱신
uv lock
```

## Architecture

진입점은 `src/main.py`이며 `python -m src.main`으로 실행한다 (relative import 때문에 직접 실행 불가).

```
Config 로드 (config.py)
  → 시크릿 마스킹 필터 설치 (SensitiveFilter)
  → 기상청 API 조회 (weather.py)
  → 에어코리아 API 조회 (air_quality.py)
  → 메시지 포맷팅 (formatter.py)
  → LINE 발송 (line_messenger.py)
  → 실패 시 sys.exit(1) → GitHub Actions fail
```

**각 모듈의 역할:**
- `config.py` — `load_config()`로 환경변수 로드·검증, `mask_secret()` 로그 마스킹 유틸, `SensitiveFilter` 로깅 필터
- `weather.py` — 기상청 단기예보 API (`getVilageFcst`). `_get_base_time(now)`으로 현재 시각 기준 최신 발표시각 계산. `WeatherData` dataclass 반환
- `air_quality.py` — 에어코리아 실시간 측정정보 API (`getCtprvnRltmMesureDnsty`). 등급 판정 로직 내장. `AirQualityData` dataclass 반환
- `formatter.py` — `WeatherData` + `AirQualityData` → LINE 메시지 문자열. 순수 함수로 구성되어 테스트 용이
- `line_messenger.py` — LINE Push Message 발송. 응답 바디 raw 로깅 금지 (토큰 노출 방지)

## Testability Pattern

`fetch_weather`와 `format_message`는 `_now: datetime | None = None` 파라미터를 통해 현재 시각을 주입받는다. 테스트에서 `requests.get`은 `unittest.mock.patch("src.weather.requests.get")`으로 모킹한다.

## GitHub Actions

- 스케줄: `cron: '0 22 * * *'` (UTC 22:00 = KST 07:00)
- 위치 설정(`LOCATION_*`, `SIDO_NAME` 등)은 GitHub **Variables** (`vars.*`)로 관리
- API 키·토큰은 GitHub **Secrets** (`secrets.*`)로 관리
- `workflow_dispatch`로 수동 실행 가능

## Security Rules

- 모든 시크릿은 `os.environ`으로만 접근. 코드·주석·테스트 어디에도 실제 값 금지
- `line_messenger.py`에서 HTTP 응답 바디를 절대 로깅하지 않는다
- 에러 메시지에 원인 상세 대신 "GitHub Actions 로그 확인" 안내만 포함

## Location Change

다른 지역으로 변경할 때는 `.env` (로컬) 또는 GitHub Variables에서 아래 5개 변수를 수정한다:
- `LOCATION_NX`, `LOCATION_NY` — 기상청 격자 좌표
- `SIDO_NAME` — 에어코리아 시도명
- `STATION_NAME` — 에어코리아 측정소명
- `LOCATION_DISPLAY_NAME` — 메시지에 표시될 지역명
