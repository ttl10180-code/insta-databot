"""경찰청 실종경보 → 실종자 찾기 카드 데이터.

안전Dream(www.safe182.go.kr)에서 발령된 실종경보를 받아온다.
공공데이터포털 키가 아니라 안전Dream에서 직접 발급하는
고유아이디(esntlId) + 인증키(authKey) 두 개가 필요하다.

주의:
  * 요청은 POST 다 (GET 이면 응답이 비어 온다).
  * result 코드 00 정상 / 80 일일 1000건 초과 / 99 필수항목 누락.
  * 이용약관상 '[자료 출처: 경찰청]' 표기가 의무다. 카드와 캡션에 넣는다.
  * 사진이 실종경보의 핵심이다. 응답에 base64 가 실려 오면 그대로 쓰고,
    없으면 안전Dream 이 공개한 이미지 주소(blobImgView.do)에서 받아
    data URI 로 박아 넣는다. 카드 렌더는 네트워크 없이 끝나야 하기 때문이다.
  * 제보는 국번없이 182 와 안전Dream 으로 안내한다.
"""
from __future__ import annotations

import base64
import logging
import ssl
import time
from datetime import datetime, timedelta

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

from src import config
from src.common import http

log = logging.getLogger(__name__)

URL = "https://www.safe182.go.kr/api/lcm/amberList.do"
PHOTO_URL = "https://www.safe182.go.kr/blobImgView.do"


class _LegacyTLSAdapter(HTTPAdapter):
    """안전Dream 서버의 TLS 설정이 오래돼서 요즘 OpenSSL 기본값으로는
    핸드셰이크가 거절된다(SSLV3_ALERT_HANDSHAKE_FAILURE).
    보안수준만 한 단계 낮추고 인증서 검증은 그대로 둔다."""

    def init_poolmanager(self, *args, **kwargs):
        ctx = create_urllib3_context(ciphers="DEFAULT@SECLEVEL=1")
        ctx.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)


def _session() -> requests.Session:
    s = requests.Session()
    s.mount("https://www.safe182.go.kr", _LegacyTLSAdapter())
    s.headers["User-Agent"] = "insta-databot/1.0"
    return s

# 대상 구분 코드 → 카드에 쓸 짧은 말
TARGET_LABEL = {
    "010": "아동", "020": "가출인", "040": "무연고자",
    "060": "지적장애", "061": "지적장애", "062": "지적장애",
    "070": "치매", "080": "기타",
}

MAX_ITEMS = 3          # 얼굴이 커야 알아본다. 한 장에 3명까지만.
LOOKBACK_DAYS = 365          # 실종경보는 오래 열려 있는 건이 많다
ROW_SIZE = 100


def _post(params: dict) -> dict:
    """안전Dream 은 국내 기관 서버라 해외 러너에서 간헐적으로 연결이 안 된다.
    (되는 때도 있고 연결 타임아웃이 나는 때도 있다 — 지수 백오프로 버틴다.)"""
    body = dict(params,
                esntlId=config.SAFE182_ESNTL_ID,
                authKey=config.SAFE182_AUTH_KEY)
    last: Exception | None = None
    for attempt in range(1, http.MAX_RETRIES + 1):
        try:
            r = _session().post(URL, data=body, timeout=http.DEFAULT_TIMEOUT)
            r.raise_for_status()
            doc = http._parse(r.text)
            return doc if isinstance(doc, dict) else {}
        except requests.RequestException as e:
            last = e
            if attempt < http.MAX_RETRIES:
                wait = http.BACKOFF ** attempt
                log.warning("안전Dream 연결 실패(%s/%s) · %.1fs 후 재시도",
                            attempt, http.MAX_RETRIES, wait)
                time.sleep(wait)
    raise http.PortalError("99", f"안전Dream 에 연결하지 못했습니다: {last}")


def _check(doc: dict) -> None:
    code = str(doc.get("result") or "")
    msg = str(doc.get("msg") or "")
    if code == "80":
        raise http.NoData("80", "안전Dream 일일 조회 한도(1000건)를 넘었습니다")
    if code == "99":
        raise http.PortalError("99", f"필수항목 누락: {msg}")
    if code and code != "00":
        raise http.PortalError(code, msg or "안전Dream 응답 오류")


def _ymd(d: datetime) -> str:
    return d.strftime("%Y-%m-%d")


def _fetch_rows(now: datetime) -> list[dict]:
    """발생일 범위로 먼저 시도하고, 안 되면 조건 없이 최신 목록을 받는다."""
    since, until = now - timedelta(days=LOOKBACK_DAYS), now
    attempts = [
        {"rowSize": ROW_SIZE, "page": 1,
         "detailDate1": _ymd(since), "detailDate2": _ymd(until)},
        {"rowSize": ROW_SIZE, "page": 1},
    ]
    for params in attempts:
        doc = _post(params)
        _check(doc)
        rows = [r for r in http.as_list(doc.get("list")) if isinstance(r, dict)]
        if rows:
            log.info("실종경보 %d건 (전체 %s건)", len(rows), doc.get("totalCount"))
            # 응답 필드명은 문서에 다 나와 있지 않다. 한 번은 찍어 둔다.
            log.info("응답 필드: %s", sorted(rows[0].keys()))
            return rows
        log.info("실종경보 조회 0건 · params=%s", sorted(params))
    return []


def _b64_photo(row: dict) -> str | None:
    """응답에 사진이 base64 로 실려 오는 경우."""
    for key in ("tknphotoFile", "tknphoto", "photo", "file2", "photoFile"):
        raw = row.get(key)
        if isinstance(raw, str) and len(raw) > 512:
            if raw.startswith("data:"):
                return raw
            return "data:image/jpeg;base64," + raw.strip()
    return None


def _fetch_photo(row: dict) -> str | None:
    """안전Dream 공개 이미지 주소에서 받아 data URI 로 만든다."""
    idn = str(row.get("msspsnIdntfccd") or "").strip()
    rpt = str(row.get("rptDscd") or "").strip()
    if not idn:
        return None
    r = None
    for attempt in (1, 2):
        try:
            r = _session().get(PHOTO_URL,
                               params={"msspsnIdntfccd": idn, "rptDscd": rpt},
                               timeout=http.DEFAULT_TIMEOUT,
                               headers={"Referer": "https://www.safe182.go.kr/"})
            r.raise_for_status()
            break
        except requests.RequestException as e:
            if attempt == 2:
                log.info("사진을 받지 못했습니다 (%s): %s", idn, e)
                return None
            time.sleep(2)
    if r is None:
        return None
    if not r.content or not r.headers.get("Content-Type", "").startswith("image"):
        return None
    mime = r.headers["Content-Type"].split(";")[0]
    return f"data:{mime};base64," + base64.b64encode(r.content).decode()


def _photo(row: dict) -> str | None:
    return _b64_photo(row) or _fetch_photo(row)


def _age(row: dict) -> str:
    now_age = str(row.get("ageNow") or "").strip()
    then_age = str(row.get("age") or "").strip()
    if now_age and then_age and now_age != then_age:
        return f"당시 {then_age}세 · 현재 {now_age}세"
    return f"{now_age or then_age}세" if (now_age or then_age) else "나이 미상"


def _date_label(raw: str) -> str:
    raw = str(raw or "").replace("-", "").strip()
    for fmt in ("%Y%m%d", "%Y%m%d%H%M%S"):
        try:
            d = datetime.strptime(raw[:len(datetime.now().strftime(fmt))], fmt)
        except ValueError:
            continue
        return f"{d.year}.{d.month}.{d.day}"
    return "-"


def _years_since(raw: str, now: datetime) -> int | None:
    raw = str(raw or "").replace("-", "").strip()[:8]
    try:
        d = datetime.strptime(raw, "%Y%m%d")
    except ValueError:
        return None
    return max(0, (now.replace(tzinfo=None) - d).days // 365)


def fetch(now: datetime | None = None) -> dict:
    if not (config.SAFE182_ESNTL_ID and config.SAFE182_AUTH_KEY):
        raise http.NoData("03", "SAFE182_ESNTL_ID / SAFE182_AUTH_KEY 가 없습니다")

    now = now or datetime.now(config.KST)
    rows = _fetch_rows(now)
    if not rows:
        raise http.NoData("03", "현재 발령된 실종경보가 없습니다")

    # 최근 실종부터
    rows.sort(key=lambda r: str(r.get("occrde") or ""), reverse=True)

    items, with_photo = [], 0
    for r in rows:
        if len(items) >= MAX_ITEMS:
            break
        photo = _photo(r)
        if photo:
            with_photo += 1
        occ = str(r.get("occrde") or "")
        items.append({
            "photo": photo,
            "name": str(r.get("nm") or "이름 비공개").strip(),
            "age": _age(r),
            "sex": str(r.get("sexdstnDscd") or "").strip() or "-",
            "target": TARGET_LABEL.get(str(r.get("writngTrgetDscd") or "").strip(), "실종자"),
            "place": str(r.get("occrAdres") or "장소 미상").strip(),
            "day": _date_label(occ),
            "years": _years_since(occ, now),
            "feature": " · ".join(x for x in [
                str(r.get("height") or "").strip() and f"{r.get('height')}cm",
                str(r.get("frmDscd") or "").strip(),
                str(r.get("hairshpeDscd") or "").strip(),
                str(r.get("alldressingDscd") or "").strip(),
            ] if x and x != "불상") or "특징 정보 없음",
        })

    # 사진 있는 사람을 앞으로 (얼굴이 먼저 보여야 한다)
    items.sort(key=lambda i: 0 if i["photo"] else 1)
    head = items[0]
    long_cases = sum(1 for i in items if (i["years"] or 0) >= 5)
    return {
        "date_label": f"{now.month}월 {now.day}일",
        "head": head,
        "items": items,
        "rest": items[1:],
        "count": len(rows),
        "shown": len(items),
        "with_photo": with_photo,
        "long_cases": long_cases,
    }
