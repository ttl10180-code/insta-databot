# 셋업 가이드

처음부터 첫 게시까지 순서대로 따라가면 됩니다.
**A → B → C → D** 순서를 지키세요. 뒤 단계가 앞 단계 결과를 씁니다.

전체 소요 시간은 대략 이렇습니다.

| 단계 | 내용 | 소요 |
|---|---|---|
| A | 공공데이터포털 API 키 발급 | 10분 (자동승인) |
| B | 인스타그램 프로페셔널 계정 + Meta 앱 | 30~40분 |
| C | GitHub 저장소 · Pages · Secrets | 15분 |
| D | 첫 게시 테스트 | 10분 |

---

## A. 공공데이터포털 API 키

`https://www.data.go.kr` 로그인 후, 아래 3개(+ 선택 1개) 데이터를 **활용신청**합니다.
개발단계는 **자동승인**이라 신청 즉시 키가 나옵니다.

| 카드 | 데이터셋 | 링크 |
|---|---|---|
| 날씨 | 기상청_단기예보 ((구)_동네예보) 조회서비스 | https://www.data.go.kr/data/15084084/openapi.do |
| 대기질 | 한국환경공단_에어코리아_대기오염정보 | https://www.data.go.kr/data/15073861/openapi.do |
| 부동산 | 국토교통부_아파트 매매 실거래가 상세 자료 | https://www.data.go.kr/data/15126468/openapi.do |

각 페이지에서 **[활용신청]** → 활용목적 간단히 입력 → 신청.

신청이 끝나면 **마이페이지 > 데이터활용 > 인증키 발급현황** 에서
**일반 인증키(Decoding)** 를 복사합니다.

> ⚠️ 반드시 **Decoding** 키입니다. Encoding 키를 쓰면 `SERVICE_KEY_IS_NOT_REGISTERED_ERROR`(코드 30)가 납니다.
> 이 프로젝트는 `requests` 가 키를 자동 인코딩하므로 Decoding 키가 맞습니다.

> ⚠️ 발급 직후 최대 1시간 정도 키가 전파되지 않아 같은 오류가 날 수 있습니다.
> 30분쯤 뒤 다시 시도해 보세요.

**호출 한도** — 개발계정 기준 기상청·실거래가 10,000건/일, 에어코리아 **500건/일**.
이 프로젝트는 하루 몇 건만 쓰므로 넉넉합니다.

### A-2. 오피넷 (유가 카드를 쓸 경우에만)

유가 API는 공공데이터포털에 'LINK'로만 등록되어 있고, 실제 키는 오피넷에서 따로 발급합니다.

1. https://www.opinet.co.kr/user/custapi/custApiInfo.do 접속 → 회원가입/로그인
2. 일반 API 신청 → **즉시 발급**
3. 발급받은 키가 `OPINET_KEY` 입니다. (일 300회 제한)

유가 카드를 쓰지 않으려면 `weekday-oil.yml` 워크플로를 삭제하거나 비활성화하면 됩니다.

---

## B. 인스타그램 자동 게시 준비

### B-1. 계정 전환

인스타그램 앱 → 설정 → 계정 유형 → **프로페셔널 계정(비즈니스 또는 크리에이터)** 으로 전환.
개인 계정은 API 게시가 불가능합니다.

### B-2. 로그인 경로 선택 — **Facebook Login 권장**

두 가지 방식이 있습니다. 무인 자동화에는 **Facebook Login** 이 유리합니다.

| | **Facebook Login** (권장) | Instagram Login |
|---|---|---|
| 페이스북 페이지 | **필요** | 불필요 |
| 토큰 만료 | **페이지 토큰은 만료 없음** | 60일마다 갱신 필요 |
| 갱신 워크플로 | 불필요 | 필요 (`refresh-token.yml`) |
| `IG_LOGIN_MODE` | `facebook` | `instagram` |

토큰이 만료되면 자동 게시가 통째로 멈추므로, 페이지를 하나 만드는 수고를 들여서라도
Facebook Login 쪽이 운영이 편합니다. 아래는 Facebook Login 기준입니다.

1. 페이스북 페이지를 하나 만듭니다 (비공개로 두어도 됩니다).
2. 인스타그램 앱 → 설정 → **계정 연결** 에서 그 페이지를 연결합니다.

### B-3. Meta 앱 만들기

1. https://developers.facebook.com/apps → **앱 만들기**
2. 사용 사례: **Instagram** 선택 → **Instagram API setup with Facebook Login**
3. 제품에 **Instagram** 추가
4. 앱 설정 > 기본 설정에서 **앱 ID / 앱 시크릿** 을 복사해 둡니다 → `IG_APP_ID`, `IG_APP_SECRET`

> **앱 검수(App Review)는 필요 없습니다.**
> 본인 계정에만 게시하는 경우, 앱이 **개발 모드**이고 본인이 앱의 관리자/테스터이면
> 실제 게시가 됩니다. 검수는 다른 사용자 계정을 연결시키는 서비스를 만들 때만 필요합니다.

### B-4. 토큰 발급

1. https://developers.facebook.com/tools/explorer (그래프 API 탐색기) 접속
2. 우상단에서 만든 앱 선택
3. 권한에 다음을 추가:
   - `instagram_basic`
   - `instagram_content_publish`
   - `pages_show_list`
   - `pages_read_engagement`
4. **Generate Access Token** → 페이스북 로그인 및 권한 승인
5. 나온 토큰으로 아래를 순서대로 호출합니다.

```bash
# (1) 단기 토큰 → 장기 사용자 토큰 (약 60일)
curl -s "https://graph.facebook.com/v26.0/oauth/access_token\
?grant_type=fb_exchange_token\
&client_id=<앱ID>\
&client_secret=<앱시크릿>\
&fb_exchange_token=<탐색기에서_받은_토큰>"

# (2) 내 페이지 목록과 페이지 토큰 (이 토큰은 만료되지 않는다)
curl -s "https://graph.facebook.com/v26.0/me/accounts?access_token=<장기_사용자_토큰>"

# (3) 페이지에 연결된 인스타그램 계정 ID
curl -s "https://graph.facebook.com/v26.0/<페이지ID>\
?fields=instagram_business_account&access_token=<페이지_토큰>"
```

- (2)에서 나온 **페이지 액세스 토큰** → `IG_ACCESS_TOKEN`
- (3)에서 나온 `instagram_business_account.id` → `IG_USER_ID`

> 페이지 토큰은 만료되지 않지만, 비밀번호 변경이나 권한 취소 시 무효화됩니다.
> 그때는 위 과정을 다시 한 번 하면 됩니다.

---

## C. GitHub 저장소 설정

### C-1. 저장소 만들고 코드 올리기

```bash
cd insta-databot
git init
git add .
git commit -m "공공데이터 인스타 카드 자동화 초기 구성"
git branch -M main
git remote add origin https://github.com/<계정>/insta-databot.git
git push -u origin main
```

> 저장소는 **Public** 으로 두는 쪽이 간단합니다.
> 인스타그램이 이미지를 내려받으려면 GitHub Pages 가 공개되어야 하는데,
> Private 저장소는 무료 플랜에서 Pages 공개 호스팅이 제한됩니다.
> 키는 전부 Secrets 에 들어가므로 코드가 공개돼도 문제없습니다.

### C-2. GitHub Pages 켜기

저장소 **Settings → Pages**

- Source: **Deploy from a branch**
- Branch: **gh-pages** / **/ (root)**
- Save

> `gh-pages` 브랜치는 첫 워크플로 실행 때 자동으로 만들어집니다.
> 브랜치 목록에 아직 없으면, 먼저 D-1 의 미리보기 실행을 한 번 돌린 뒤 다시 설정하세요.

주소는 `https://<계정>.github.io/insta-databot` 형태가 됩니다.

### C-3. Secrets 등록

**Settings → Secrets and variables → Actions → Secrets 탭 → New repository secret**

| 이름 | 값 |
|---|---|
| `DATA_GO_KR_KEY` | 공공데이터포털 일반 인증키(**Decoding**) |
| `OPINET_KEY` | 오피넷 키 (유가 카드를 쓸 때만) |
| `IG_USER_ID` | 인스타그램 비즈니스 계정 ID |
| `IG_ACCESS_TOKEN` | 페이지 액세스 토큰 |
| `IG_APP_ID` | Meta 앱 ID |
| `IG_APP_SECRET` | Meta 앱 시크릿 |
| `GH_PAT` | (선택) Instagram Login 을 쓸 때 토큰 자동 갱신용 PAT |

### C-4. Variables 등록

같은 화면의 **Variables 탭 → New repository variable**

| 이름 | 값 예시 | 설명 |
|---|---|---|
| `PUBLIC_BASE_URL` | `https://<계정>.github.io/insta-databot` | **끝에 / 없이** |
| `CARD_HANDLE` | `@daily.data.kr` | 카드 우하단에 찍히는 계정명 |
| `IG_LOGIN_MODE` | `facebook` | 또는 `instagram` |
| `IG_API_VERSION` | `v26.0` | |
| `WEATHER_REGION` | `서울` | 카드 제목에 들어감 |
| `WEATHER_NX` | `60` | 기상청 격자 X |
| `WEATHER_NY` | `127` | 기상청 격자 Y |
| `AIR_SIDO` | `서울` | |
| `REALESTATE_LAWD_CDS` | `11680,11650,11710,11440,11560` | 강남·서초·송파·마포·영등포 |
| `OPINET_AREA` | `01` | 01 = 서울 |

Variables 는 값이 없어도 코드 기본값으로 동작하지만, `PUBLIC_BASE_URL` 만은 **반드시** 넣어야 합니다.

주요 자치구 격자 좌표와 법정동코드는 [docs/REFERENCE.md](docs/REFERENCE.md) 에 정리해 두었습니다.

---

## D. 첫 게시까지

### D-1. 디자인 먼저 확인 (키 없이 가능)

Actions 탭 → **디자인 미리보기 (샘플 데이터)** → Run workflow
→ 완료 후 Artifacts 에서 `preview-cards` 다운로드.

로컬에서 보려면:

```bash
pip install -r requirements.txt
python -m playwright install chromium
python -m src.main render weather air realestate oil --sample
open out/            # macOS
```

### D-2. 키 점검

```bash
cp .env.example .env     # 값 채우기
python scripts/check.py
```

모든 항목에 ✅ 가 떠야 합니다. ❌ 가 있으면 [문제 해결](#문제-해결) 을 보세요.

### D-3. 게시 없이 전체 파이프라인 돌려보기

Actions → **매일 아침 · 날씨 + 대기질** → Run workflow → `dry_run` **체크** → 실행.

실데이터로 카드가 만들어지고 gh-pages 까지 올라가지만 게시는 하지 않습니다.
Artifacts 의 이미지와 `https://<계정>.github.io/insta-databot` 접속을 확인하세요.

### D-4. 진짜 게시

같은 워크플로를 `dry_run` **해제** 하고 실행합니다.
성공하면 로그에 `✅ 게시 완료 media_id=...` 가 찍히고 인스타그램에 올라갑니다.

이후로는 스케줄대로 자동 실행됩니다.

| 워크플로 | 시각 (KST) |
|---|---|
| 날씨 + 대기질 (캐러셀 2장) | 매일 07:30 |
| 유가 | 평일 08:00 |
| 아파트 실거래 | 매주 월요일 09:00 |

> GitHub Actions 의 스케줄은 부하 상황에 따라 **5~20분 정도 늦게** 실행될 수 있습니다.
> 정확한 정시 발행이 필요하면 조금 앞당겨 설정하세요.

---

## 문제 해결

**`SERVICE_KEY_IS_NOT_REGISTERED_ERROR` (코드 30)**
Encoding 키를 넣었거나, 발급 직후 전파가 안 된 상태입니다.
Decoding 키인지 확인하고 30분 뒤 재시도하세요.

**`LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS` (코드 22)**
일일 호출 한도 초과. 에어코리아는 500건/일로 가장 빡빡합니다.

**인스타그램 `9004` / `2207052` — 이미지를 가져오지 못함**
가장 흔한 오류입니다. 순서대로 확인하세요.
1. `PUBLIC_BASE_URL` 끝에 `/` 가 붙어 있지 않은지
2. GitHub Pages 가 **gh-pages 브랜치**로 설정되어 있는지
3. 브라우저 시크릿 창에서 카드 URL 이 실제로 열리는지
4. 저장소가 Private 은 아닌지

**인스타그램 `2207009` — 종횡비 오류**
카드가 1080x1080 이 아닙니다. 템플릿을 수정했다면 캔버스 크기를 확인하세요.

**`OAuthException` / 토큰 만료**
Instagram Login 을 쓰고 있는데 60일이 지났을 가능성이 큽니다.
Actions → **인스타그램 토큰 갱신** 을 수동 실행하거나, B-4 를 다시 수행하세요.

**카드의 한글이 □□□ 로 나옴**
본문 폰트는 저장소에 포함되어 있어 이 문제가 나지 않아야 합니다.
이모지만 깨진다면 워크플로의 `fonts-noto-color-emoji` 설치 단계가 빠진 것입니다.

**실거래가 카드의 수치가 며칠 뒤 달라짐**
정상입니다. 실거래 신고 기한이 계약 후 30일이라 최근 월 데이터는 계속 갱신됩니다.
계약 해제된 거래(`cdealType=O`)는 이미 집계에서 제외하고 있습니다.
