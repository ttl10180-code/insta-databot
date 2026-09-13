"""검증 테스트 — API 키 없이 전부 실행된다.

  python -m pytest tests -q      (pytest 있을 때)
  python tests/test_pipeline.py  (없을 때)
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image                                   # noqa: E402

from src import config, sample                          # noqa: E402
from src.common import http, render                     # noqa: E402
from src.sources import realestate, weather             # noqa: E402

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = ""):
    print(("  ✅ " if cond else "  ❌ ") + name + (f" — {detail}" if detail else ""))
    if not cond:
        FAILS.append(name)


# ---------------------------------------------------------------- 발표 회차
def test_base_time():
    print("\n[기상청 발표 회차 계산]")
    cases = [
        (datetime(2026, 9, 12, 7, 30), "20260912", "0500"),
        (datetime(2026, 9, 12, 5, 5),  "20260912", "0200"),   # 05:10 전 → 02시 회차
        (datetime(2026, 9, 12, 5, 15), "20260912", "0500"),
        (datetime(2026, 9, 12, 1, 30), "20260911", "2300"),   # 02시 전 → 전날 23시
        (datetime(2026, 9, 12, 23, 59), "20260912", "2300"),
        (datetime(2026, 9, 12, 0, 5),  "20260911", "2300"),
    ]
    for now, exp_d, exp_t in cases:
        d, t = weather.latest_base(now)
        check(f"{now:%m/%d %H:%M} → {exp_d} {exp_t}", (d, t) == (exp_d, exp_t), f"실제 {d} {t}")


# ---------------------------------------------------------------- 파싱 방어
def test_parsers():
    print("\n[결측값·타입 방어]")
    check("'-' → None", http.to_float("-") is None)
    check("'' → None", http.to_float("") is None)
    check("None → None", http.to_float(None) is None)
    check("'통신장애' → None", http.to_float("통신장애") is None)
    check("'1,234' → 1234.0", http.to_float("1,234") == 1234.0)
    check("'  350,000 ' → 350000", http.to_int("  350,000 ") == 350000)
    check("as_list(dict) → 길이 1", len(http.as_list({"a": 1})) == 1)
    check("as_list(None) → 빈 리스트", http.as_list(None) == [])
    check("as_list(list) → 그대로", len(http.as_list([1, 2, 3])) == 3)

    print("\n[게이트웨이 XML 오류 인식]")
    xml = ("<OpenAPI_ServiceResponse><cmmMsgHeader>"
           "<returnReasonCode>30</returnReasonCode>"
           "<errMsg>SERVICE KEY IS NOT REGISTERED ERROR.</errMsg>"
           "</cmmMsgHeader></OpenAPI_ServiceResponse>")
    try:
        http._parse(xml)
        check("XML 오류를 예외로 변환", False, "예외가 발생하지 않음")
    except http.PortalError as e:
        check("XML 오류를 예외로 변환", e.code == "30", f"code={e.code}")

    print("\n[서비스 레벨 resultCode]")
    try:
        http._check_header({"response": {"header": {"resultCode": "03", "resultMsg": "NODATA"}}})
        check("NODATA 를 NoData 로 구분", False)
    except http.NoData:
        check("NODATA 를 NoData 로 구분", True)
    http._check_header({"response": {"header": {"resultCode": "00", "resultMsg": "OK"}}})
    check("정상 코드는 통과", True)


# ---------------------------------------------------------------- 실거래 파싱
def test_realestate_parse():
    print("\n[실거래 응답 파싱]")
    ok = realestate._parse_deal({
        "aptNm": "래미안", "umdNm": "대치동", "excluUseAr": "84.97",
        "dealAmount": "    350,000", "floor": "12", "dealDay": "14",
        "cdealType": "",
    }, "11680")
    check("공백·콤마 금액 파싱", ok and ok["man_won"] == 350000, str(ok and ok["man_won"]))
    check("구 이름 매핑", ok and ok["gu"] == "강남구")
    check("평당가 계산", ok and 13000 < ok["per_pyeong"] < 14500, str(ok and ok["per_pyeong"]))

    cancelled = realestate._parse_deal({
        "aptNm": "취소건", "umdNm": "대치동", "excluUseAr": "84.97",
        "dealAmount": "999,999", "floor": "1", "dealDay": "1", "cdealType": "O",
    }, "11680")
    check("해제 거래 제외", cancelled is None)
    check("전월 계산 (202601 → 202512)", realestate._prev_month("202601") == "202512")
    check("전월 계산 (202609 → 202608)", realestate._prev_month("202609") == "202608")


# ---------------------------------------------------------------- 렌더링
def test_render():
    print("\n[카드 렌더링 — 인스타그램 요건]")
    now = datetime(2026, 9, 12, 7, 30, tzinfo=config.KST)
    for kind in ["weather", "air", "realestate", "oil"]:
        template, ctx, caption = sample.build(kind, now)
        path = render.render_card(template, ctx, config.OUT_DIR / f"test-{kind}.jpg")
        im = Image.open(path)
        size_kb = path.stat().st_size / 1024
        check(f"{kind}: 1080x1080", im.size == (1080, 1080), str(im.size))
        check(f"{kind}: JPEG / RGB", im.format == "JPEG" and im.mode == "RGB",
              f"{im.format}/{im.mode}")
        check(f"{kind}: 8MB 미만", path.stat().st_size < 8 * 1024 * 1024, f"{size_kb:.0f}KB")
        check(f"{kind}: 캡션 2200자 이내", len(caption) <= 2200, f"{len(caption)}자")
        check(f"{kind}: 캡션에 출처 표기", "출처" in caption)


# ------------------------------------------------- 긴 텍스트에도 레이아웃 유지
def test_overflow_guard():
    print("\n[긴 텍스트 넘침 방지]")
    now = datetime(2026, 9, 12, 7, 30, tzinfo=config.KST)
    template, ctx, _ = sample.build("realestate", now)
    ctx["title"] = "제목이 아주 많이 길어졌을 때에도 레이아웃이 무너지지 않는지 확인하는 아주 긴 제목입니다"
    ctx["subtitle"] = "부제 역시 대단히 길게 들어오는 경우를 가정하여 한 줄로 잘리는지 확인합니다"
    ctx["d"] = dict(ctx["d"])
    ctx["d"]["top"] = [
        {"name": "이름이아주긴아파트단지명이들어오는경우를가정한테스트단지",
         "dong": "영등포구 여의도동 아주 긴 법정동 이름", "area": 134.9, "floor": 33,
         "price": "123.4억"} for _ in range(3)
    ]
    path = render.render_card(template, ctx, config.OUT_DIR / "test-overflow.jpg")
    im = Image.open(path)
    check("긴 텍스트에도 1080x1080 유지", im.size == (1080, 1080), str(im.size))
    print(f"      → 육안 확인용: {path}")


def main() -> int:
    test_base_time()
    test_parsers()
    test_realestate_parse()
    test_render()
    test_overflow_guard()
    print("\n" + ("=" * 56))
    if FAILS:
        print(f"❌ 실패 {len(FAILS)}건:")
        for f in FAILS:
            print("   -", f)
        return 1
    print("✅ 전체 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
