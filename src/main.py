"""진입점.

  python -m src.main render weather          # 카드만 생성 (API 키 있으면 실데이터)
  python -m src.main render weather --sample # 샘플 데이터로 디자인 확인 (키 불필요)
  python -m src.main post weather            # 생성 + 인스타그램 게시
  python -m src.main post weather air --carousel
  python -m src.main refresh-token           # 장기 토큰 갱신
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from src import cards, config, sample
from src.common import instagram, render

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s · %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("databot")


def make_card(kind: str, now: datetime, use_sample: bool):
    if use_sample:
        template, ctx, caption = sample.build(kind, now)
    else:
        template, ctx, caption = cards.CARDS[kind](now)
    stamp = now.strftime("%Y%m%d")
    out = config.OUT_DIR / f"{stamp}-{kind}.jpg"
    path = render.render_card(template, ctx, out)
    return path, caption


def public_url(path) -> str:
    if not config.PUBLIC_BASE_URL:
        raise SystemExit(
            "[설정 오류] PUBLIC_BASE_URL 이 비어 있습니다.\n"
            "인스타그램은 공개 HTTPS 이미지 URL 만 받습니다. SETUP.md 의 GitHub Pages 설정을 참고하세요."
        )
    return f"{config.PUBLIC_BASE_URL}/cards/{path.name}"


def cmd_render(args) -> int:
    now = datetime.now(config.KST)
    results = []
    for kind in args.kinds:
        path, caption = make_card(kind, now, args.sample)
        results.append({"kind": kind, "file": str(path), "caption": caption})
        print(f"✅ {kind}: {path}")
    (config.OUT_DIR / "captions.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def load_rendered(kinds: list[str]):
    """render 단계에서 만들어 둔 결과를 재사용한다 (재렌더 방지)."""
    manifest = config.OUT_DIR / "captions.json"
    if not manifest.exists():
        raise SystemExit(f"[오류] {manifest} 가 없습니다. 먼저 render 를 실행하세요.")
    rows = {r["kind"]: r for r in json.loads(manifest.read_text(encoding="utf-8"))}
    made = []
    for kind in kinds:
        r = rows.get(kind)
        if not r:
            log.error("%s 는 render 결과에 없습니다. 건너뜁니다.", kind)
            continue
        path = Path(r["file"])
        if not path.exists():
            log.error("%s 이미지가 없습니다: %s", kind, path)
            continue
        made.append((kind, path, r["caption"]))
    return made


def cmd_post(args) -> int:
    now = datetime.now(config.KST)
    config.require("IG_USER_ID", "IG_ACCESS_TOKEN")

    left = instagram.remaining_quota()
    if left is not None:
        log.info("24시간 게시 한도 잔여: %s", left)
        if left <= 0:
            log.error("게시 한도를 모두 사용했습니다. 오늘은 중단합니다.")
            return 2

    if args.reuse:
        made = load_rendered(args.kinds)
    else:
        made = []
        for kind in args.kinds:
            try:
                made.append((kind, *make_card(kind, now, args.sample)))
            except Exception as e:                # noqa: BLE001
                log.error("%s 카드 생성 실패, 건너뜁니다: %s", kind, e)
    if not made:
        log.error("생성된 카드가 없습니다.")
        return 1

    if config.DRY_RUN:
        for kind, path, _ in made:
            log.info("[DRY_RUN] 게시 생략: %s → %s", kind, public_url(path))
        return 0

    if args.carousel and len(made) >= 2:
        urls = [public_url(p) for _, p, _ in made]
        caption = made[0][2]
        media_id = instagram.publish_carousel(urls, caption)
        print(f"✅ 캐러셀 게시 완료 media_id={media_id}")
        return 0

    failed = 0
    for kind, path, caption in made:
        try:
            media_id = instagram.publish_image(public_url(path), caption)
            print(f"✅ {kind} 게시 완료 media_id={media_id}")
        except Exception as e:                    # noqa: BLE001
            log.error("%s 게시 실패: %s", kind, e)
            failed += 1
    return 1 if failed else 0


def cmd_refresh_token(args) -> int:
    payload = instagram.refresh_long_lived_token()
    token = payload.get("access_token", "")
    expires = payload.get("expires_in")
    print(json.dumps({"access_token": token, "expires_in": expires}, ensure_ascii=False))
    log.info("토큰 갱신 완료 (유효기간 %s초 ≈ %s일)", expires,
             round(int(expires) / 86400) if expires else "?")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="databot", description="공공데이터 → 인스타 카드 자동화")
    sub = p.add_subparsers(dest="cmd", required=True)

    kinds = list(cards.CARDS)

    r = sub.add_parser("render", help="카드 이미지만 생성")
    r.add_argument("kinds", nargs="+", choices=kinds)
    r.add_argument("--sample", action="store_true", help="샘플 데이터로 디자인 확인 (API 키 불필요)")
    r.set_defaults(func=cmd_render)

    o = sub.add_parser("post", help="카드 생성 후 인스타그램 게시")
    o.add_argument("kinds", nargs="+", choices=kinds)
    o.add_argument("--carousel", action="store_true", help="여러 장을 캐러셀 한 게시물로")
    o.add_argument("--sample", action="store_true")
    o.add_argument("--reuse", action="store_true",
                   help="render 로 만들어 둔 이미지를 재사용 (CI 기본 경로)")
    o.set_defaults(func=cmd_post)

    t = sub.add_parser("refresh-token", help="인스타그램 장기 토큰 갱신")
    t.set_defaults(func=cmd_refresh_token)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
