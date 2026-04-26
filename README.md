# 🌅 Weather Alarm

매일 아침 7시(KST)에 당일 날씨, 미세먼지, 공기질 정보를 LINE으로 자동 발송하는 앱입니다.

---

## ⚠️ 보안 안내 (반드시 읽어주세요)

- 이 프로젝트를 Fork/Clone 한 경우 **반드시 본인의 API 키를 새로 발급**하여 사용하세요.
- **API 키, LINE 토큰, User ID를 절대 커밋하지 마세요.** `.env` 파일은 `.gitignore`에 포함되어 있습니다.
- `pre-commit` hook 설치를 권장합니다. 커밋 전 시크릿 패턴을 자동으로 감지합니다.

```bash
uv run pre-commit install
```

---

## 메시지 예시

```
🌅 오늘의 날씨
📅 2026.04.26 (일)
📍 경기도 성남시 분당구

[날씨]
⛅ 하늘: 구름많음
🌡 기온: 18°C (최저 12°C / 최고 23°C)
💧 습도: 55%
🌬 바람: 3.2m/s
☔ 강수확률: 20%

[공기질]
오전
😷 미세먼지(PM10): 35㎍/㎥ (보통)
🫁 초미세먼지(PM2.5): 18㎍/㎥ (보통)
🌫 통합대기지수: 65 (보통)

오후
😷 미세먼지(PM10): 35㎍/㎥ (보통)
🫁 초미세먼지(PM2.5): 18㎍/㎥ (보통)
🌫 통합대기지수: 65 (보통)
```

---

## 사전 준비물

### 1. 기상청 공공데이터포털 API 키

1. [data.go.kr](https://www.data.go.kr) 회원가입 후 로그인
2. **기상청_단기예보 ((구)동네예보) 조회서비스** 검색 → 활용신청
3. 마이페이지 → 일반 인증키(Decoding) 복사

### 2. 에어코리아 API 키

1. 동일하게 [data.go.kr](https://www.data.go.kr) 로그인
2. **한국환경공단_에어코리아_대기오염정보** 검색 → 활용신청
3. 마이페이지 → 일반 인증키(Decoding) 복사
4. ※ 기상청과 에어코리아 API 키는 동일한 포털이지만 **신청은 각각** 해야 합니다.

### 3. LINE Messaging API 채널 생성

1. [LINE Developers](https://developers.line.biz) → 콘솔 로그인
2. **Provider 생성** → **채널 생성** → Messaging API 선택
3. 채널 기본 설정 → **Channel access token** 발급 (Long-lived)
4. 채널 기본 설정 → **Channel secret** 확인 (선택 사항)

### 4. 본인 LINE User ID 확인

LINE Developers 콘솔에서 **봇과 대화**를 시작한 뒤 Webhook 로그로 확인하거나,
아래 curl 명령으로 봇 팔로워를 조회할 수 있습니다.

```bash
# LINE Bot에 친구 추가 후 아래 명령 실행 (응답에 userId 포함)
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://api.line.me/v2/bot/followers/ids
```

---

## 로컬 실행

### 1. 저장소 클론 및 의존성 설치

```bash
git clone https://github.com/YOUR_USERNAME/weather-alarm.git
cd weather-alarm

uv venv        # 가상환경 생성
uv sync        # 의존성 설치
```

### 2. 환경변수 설정

```bash
cp .env.example .env
```

`.env` 파일을 열어 실제 값을 입력합니다:

```dotenv
KMA_API_KEY=발급받은_기상청_API_키
AIRKOREA_API_KEY=발급받은_에어코리아_API_키
LINE_CHANNEL_ACCESS_TOKEN=발급받은_LINE_토큰
LINE_USER_ID=본인_LINE_User_ID
```

> **`.env` 파일이 `.gitignore`에 포함되어 있는지 반드시 확인하세요.**  
> `git check-ignore -v .env` 명령으로 확인할 수 있습니다.

### 3. pre-commit hook 설치 (권장)

```bash
uv run pre-commit install
```

커밋 전 API 키, 개인키 패턴 등을 자동으로 탐지합니다.

### 4. 실행

```bash
uv run python -m src.main
```

---

## GitHub Actions 설정

### 1. Secrets 등록

레포지토리 → **Settings → Secrets and variables → Actions → New repository secret**

| Secret 이름 | 값 |
|---|---|
| `KMA_API_KEY` | 기상청 API 키 |
| `AIRKOREA_API_KEY` | 에어코리아 API 키 |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Channel Access Token |
| `LINE_USER_ID` | 본인 LINE User ID |

### 2. Variables 등록 (위치 설정)

레포지토리 → **Settings → Secrets and variables → Actions → Variables 탭 → New repository variable**

| Variable 이름 | 기본값 (분당구) | 설명 |
|---|---|---|
| `LOCATION_NX` | `61` | 기상청 격자 X |
| `LOCATION_NY` | `120` | 기상청 격자 Y |
| `SIDO_NAME` | `경기` | 에어코리아 시도명 |
| `STATION_NAME` | `서현동` | 에어코리아 측정소명 |
| `LOCATION_DISPLAY_NAME` | `경기도 성남시 분당구` | 메시지 표시 지역명 |

> 위치 변수(민감하지 않은 값)는 Secrets 대신 Variables에 저장합니다.

### 3. Actions 활성화

레포지토리 → **Actions** 탭 → "I understand my workflows, go ahead and enable them" 클릭

### 4. 수동 테스트

Actions 탭 → **Daily Weather Briefing** → **Run workflow** → Run

---

## 수신 시간 변경

`.github/workflows/daily-briefing.yml`의 cron 표현식을 수정합니다.

```yaml
on:
  schedule:
    - cron: '0 22 * * *'   # UTC 기준 — KST = UTC + 9
```

| 원하는 KST 시각 | cron (UTC) |
|---|---|
| 매일 06:00 | `0 21 * * *` |
| 매일 07:00 | `0 22 * * *` |
| 매일 08:00 | `0 23 * * *` |

---

## 다른 지역으로 변경

GitHub Variables의 5개 값을 아래 표를 참고하여 수정합니다.

기상청 격자 좌표는 [기상청 공공데이터포털 문서](https://www.data.go.kr/data/15084084/openapi.do)의 좌표변환 자료를 참고하세요.

에어코리아 측정소명은 [에어코리아 측정소 정보](https://www.airkorea.or.kr/web/stationInfo) 페이지에서 확인할 수 있습니다.

| 지역 | NX | NY | SIDO_NAME | STATION_NAME |
|---|---|---|---|---|
| 서울 강남구 | 61 | 126 | 서울 | 강남구 |
| 서울 종로구 | 60 | 127 | 서울 | 종로구 |
| 경기 성남시 분당구 | 61 | 120 | 경기 | 서현동 |
| 경기 수원시 | 60 | 121 | 경기 | 영통구 |
| 부산 해운대구 | 99 | 75 | 부산 | 해운대구 |
| 대구 중구 | 89 | 90 | 대구 | 중구 |
| 인천 연수구 | 55 | 123 | 인천 | 연수구 |
| 대전 유성구 | 67 | 101 | 대전 | 유성구 |
| 광주 서구 | 58 | 74 | 광주 | 서구 |
| 제주시 | 53 | 38 | 제주 | 이도동 |

---

## 기여 가이드

- PR 제출 전 `git diff`로 시크릿 포함 여부를 직접 확인하세요.
- 이슈 작성 시 본인의 환경변수 값(API 키, User ID 등)을 절대 포함하지 마세요.
- `pre-commit`이 설치된 경우 커밋 시 자동으로 시크릿 패턴을 검사합니다.

---

## 라이선스

[MIT License](LICENSE)
