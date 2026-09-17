# 서울 중계기

해외 GitHub Actions 러너에서 국내 정부 서버가 안 닿는 시간대를 피하려고,
요청만 서울(Supabase Edge Function, ap-northeast-2)을 거쳐 보낸다.

## 왜

2026-09-18 00:25 KST, 같은 3분 안에서 같은 호스트를 양쪽에서 찔러본 결과다.

| 호스트 | 해외(러너) | 서울(Supabase) |
|---|---|---|
| apis.data.go.kr | 400 | 400 (0.5초) |
| www.safetydata.go.kr | 200 | 200 (0.8초) |
| www.safe182.go.kr | 200 | 200 (0.6초) |
| oapi.koreaexim.go.kr | 200 | 302 (0.5초) |
| **www.kobis.or.kr** | **연결 실패** | **200 (3.0초)** |

표본 하나짜리 비교다. 다만 이 패턴(닿는 호스트가 시간대별로 돌아가며 바뀐다)은
9월 16~17일 내내 반복해서 관찰됐고, 닿는 호스트들의 응답 시간도 서울 쪽이
5~10배 빠르다.

## 배포된 곳

- 프로젝트: `momo` (org `momo`, ap-northeast-2)
- 함수: `databot-kr`
- JWT 검사: **켜 둔다.** 이걸 끄면 아무나 쓰는 국내 정부망 중계기가 된다.

`databot-kr-probe` 는 위 표를 만든 일회성 진단 함수다. 지워도 된다.

## 켜는 법

GitHub 저장소 Settings → Secrets and variables → Actions 에 두 개를 넣는다.

| 이름 | 값 |
|---|---|
| `KR_RELAY_URL` | `https://<project-ref>.supabase.co/functions/v1/databot-kr` |
| `KR_RELAY_KEY` | Supabase 프로젝트의 **anon** 키 |

둘 다 비어 있으면 중계를 쓰지 않고 예전처럼 직접 연결한다. 중계가 실패해도
언제나 직접 연결로 되돌아간다 (`src/common/relay.py`). 새 경로가 무너졌을 때
발행 전체가 멈추면 고치려던 문제를 더 키우는 셈이기 때문이다.

## 고칠 때

이 디렉터리가 원본이다. 대시보드에서 직접 고치면 저장소와 어긋난다.
