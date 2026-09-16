# 공공데이터 → 인스타그램 카드 자동 발행

공공데이터포털 API 에서 값을 받아 **1080×1080 정보 카드**를 만들고,
인스타그램에 자동으로 게시하는 시스템입니다. GitHub Actions 스케줄로 무인 운영됩니다.

```
공공데이터 API  →  카드 데이터 정리  →  HTML 템플릿 렌더  →  JPEG
                                                              ↓
              인스타그램 게시  ←  공개 URL 확인  ←  GitHub Pages 업로드
```

## 카드 11종

실제 데이터로 발행되는 것을 확인한 카드입니다 (2026-09-16 기준).

| 카드 | 데이터 출처 | 발행 주기 |
|---|---|---|
| 오늘의 날씨 | 기상청 단기예보 | 매일 07:30 |
| 오늘의 대기질 | 한국환경공단 에어코리아 | 매일 07:30 (날씨와 캐러셀) |
| 생활기상지수 | 기상청 생활기상지수 (자외선 · 대기정체) | 매일 07:30 (캐러셀) |
| 실종자 찾기 | 경찰청 안전Dream 실종경보 | 매일 19:00 |
| 오늘의 환율 | 한국수출입은행 현재환율 | 평일 |
| 박스오피스 | 영화진흥위원회 KOBIS | 매일 09:20 |
| 주말 박스오피스 | 영화진흥위원회 KOBIS | 매주 |
| 아파트 실거래 | 국토교통부 실거래가 상세자료 | 매주 월 09:00 |
| 아파트 청약 일정 | 한국부동산원 청약홈 | 매주 |

### 보류 중인 카드 2종

스케줄을 꺼 두었고 수동 실행만 가능합니다. 해결되면 각 워크플로의
`schedule:` 주석을 풀면 됩니다.

| 카드 | 막힌 이유 | 풀리는 조건 |
|---|---|---|
| 장바구니 물가 | 공공데이터포털 API 가 `resultCode 0 / 정상` 을 주면서 `totalCount 0` 인 빈 응답만 돌려준다. 조건을 전부 떼도 같다 | KAMIS(kamis.or.kr) 직접 연동 또는 운영계정 승인 |
| 오늘의 기름값 | `OPINET_KEY` 미발급 (코드는 정상) | 오피넷에서 Open API 키를 받아 Secrets 에 `OPINET_KEY` 등록 |

### 알아둘 점 — 국내 기관 서버

kobis.or.kr, apis.data.go.kr 등은 해외 러너에서 간헐적으로 연결이 끊긴다.
모든 요청에 지수 백오프 재시도(4회)가 걸려 있지만, 가끔 실패가 난다.
카드 하나가 실패해도 같은 실행의 다른 카드는 그대로 발행된다.

한 호스트가 재시도를 전부 쓰고도 응답을 한 번도 못 받으면, 그 실행
안에서는 같은 호스트에 더 요청하지 않는다(`http.HostDown`). 이게 없으면
서버가 통째로 죽은 날에 지수 하나당 100초씩 까먹으며 20분을 흘려보낸다.

`LivingWthrIdxService` 는 포털 화면에 "4.0" 으로 적혀 있지만 실제 경로는
**V5** 다(`/LivingWthrIdxServiceV5/getUVIdxV5`). V4 로 부르면 400 이 온다.

안전Dream(safe182.go.kr)은 TLS 설정이 오래돼서 요즘 OpenSSL 기본값으로는
핸드셰이크가 거절된다. `src/sources/missing.py` 가 그 호스트에만
`SECLEVEL=1` 어댑터를 물려 쓴다 (인증서 검증은 유지).

## 디자인이 항상 같은 이유

카드의 **글씨체·크기·위치·여백·색**은 전부 `templates/tokens.css` 와 `templates/base.css`
두 파일에 고정되어 있습니다. 카드마다 바뀌는 건 액센트 색 한 줄과 슬롯에 들어가는 값뿐입니다.

레이아웃이 밀리지 않도록 3중 장치를 뒀습니다.

1. **고정 슬롯** — 헤더 62px, 타이틀 178px, 푸터 46px 의 높이가 카드 종류와 무관하게 동일합니다.
2. **자동 축소** — 제목이 길면 슬롯을 넘기는 대신 글자 크기만 줄어듭니다 (68px → 최소 44px).
3. **넘침 방지** — 본문이 그래도 길면 본문 블록만 비율을 유지한 채 축소되어, 푸터를 침범하는 일이 구조적으로 불가능합니다.

숫자는 `tabular-nums` 고정폭이라 값이 바뀌어도 자리가 흔들리지 않습니다.
한글은 `word-break: keep-all` 로 어절 단위 줄바꿈됩니다.

> Canva 연동도 검토했지만 **Autofill API 가 Canva Enterprise 전용**이고
> OAuth 리프레시 토큰이 1회용이라 무인 자동화에 맞지 않아 HTML 템플릿 방식으로 만들었습니다.
> 자세한 비교는 [docs/DECISIONS.md](docs/DECISIONS.md) 에 있습니다.

## 시작하기

**[SETUP.md](SETUP.md)** 를 순서대로 따라가세요. API 키 발급부터 첫 게시까지 전부 정리되어 있습니다.

키 없이 디자인만 먼저 보려면:

```bash
pip install -r requirements.txt
python -m playwright install chromium
python -m src.main render weather air realestate oil --sample
```

## 명령어

```bash
# 카드 이미지만 생성 (실데이터)
python -m src.main render weather air

# 샘플 데이터로 디자인 확인 (API 키 불필요)
python -m src.main render weather --sample

# 생성 + 게시
python -m src.main post weather

# 이미 만든 이미지로 캐러셀 게시 (CI 기본 경로)
python -m src.main post weather air --carousel --reuse

# 설정·연결 점검
python scripts/check.py

# 인스타그램 장기 토큰 갱신
python -m src.main refresh-token
```

`DRY_RUN=1` 을 주면 게시 직전까지만 수행하고 실제 업로드는 하지 않습니다.

## 구조

```
src/
  config.py          환경변수 · 지역 설정 · 법정동코드
  main.py            CLI 진입점
  cards.py           카드별 제목 · 부제 · 캡션 정의
  sample.py          샘플 데이터 (키 없이 디자인 확인용)
  sources/           데이터 수집 — weather / air / realestate / oil
  common/
    http.py          공공데이터포털 공통 클라이언트 (XML 에러·결측값·재시도 처리)
    render.py        HTML → 1080×1080 JPEG
    instagram.py     Content Publishing API
templates/
  tokens.css         ★ 디자인 토큰 — 폰트 · 색 · 크기
  base.css           ★ 고정 레이아웃 뼈대 · 공용 컴포넌트
  _layout.html       공통 골격 (헤더/타이틀/본문/푸터)
  *.html             카드별 본문 슬롯
fonts/               Pretendard (저장소에 포함 — CI 폰트 설치 불필요)
scripts/             Pages 배포 · 공개 확인 · 설정 점검
docs/                레퍼런스와 설계 결정 기록
```

## 카드 내용 바꾸기

- **문구·해시태그** → `src/cards.py`
- **레이아웃** → `templates/<카드>.html`
- **폰트·색·크기** → `templates/tokens.css` (여기만 고치면 4종 전부 동시에 바뀝니다)
- **지역** → 저장소 Variables 의 `WEATHER_NX/NY`, `AIR_SIDO`, `REALESTATE_LAWD_CDS`
- **발행 시각** → `.github/workflows/*.yml` 의 cron (UTC 기준, KST = UTC+9)

## 새 카드 추가하기

1. `src/sources/<이름>.py` 에 `fetch()` 작성
2. `templates/<이름>.html` 에 `{% extends "_layout.html" %}` 로 본문 슬롯만 작성
3. `src/cards.py` 에 `build_<이름>()` 추가하고 `CARDS` 에 등록
4. `src/sample.py` 에 샘플 데이터 추가

공용 컴포넌트(`.hero`, `.tile`, `.rank`, `.strip`, `.badge`)를 쓰면 기존 카드와 톤이 자동으로 맞습니다.
