"""Instagram Content Publishing API 클라이언트.

게시는 2단계다: 컨테이너 생성(POST /media) → 게시(POST /media_publish).
image_url 은 메타 서버가 직접 내려받으므로 반드시 공개 HTTPS URL 이어야 한다.
"""
from __future__ import annotations

import logging
import time

import requests

from src import config

log = logging.getLogger(__name__)

TIMEOUT = 60
POLL_INTERVAL = 3
POLL_MAX = 20


class InstagramError(RuntimeError):
    def __init__(self, payload: dict):
        err = (payload or {}).get("error", {})
        self.code = err.get("code")
        self.subcode = err.get("error_subcode")
        self.message = err.get("message", str(payload))
        super().__init__(f"[{self.code}/{self.subcode}] {self.message} — {HINTS.get(self.subcode or self.code, '')}")


HINTS = {
    2207052: "이미지 URL 을 메타가 못 받았습니다. 공개 접근 가능한 HTTPS 직접 링크인지 확인하세요.",
    2207023: "URL 이 이미지 파일이 아닙니다(HTML 반환 등).",
    2207004: "이미지 용량이 8MB 를 넘습니다.",
    2207009: "종횡비가 4:5 ~ 1.91:1 범위를 벗어났습니다.",
    2207005: "지원하지 않는 포맷입니다. JPEG 로 변환하세요.",
    2207020: "컨테이너가 24시간을 넘겨 만료되었습니다. 새로 생성하세요.",
    2207042: "24시간 게시 한도를 초과했습니다.",
    2207051: "스팸으로 의심되어 차단되었습니다. 캡션/빈도를 조정하세요.",
    2207010: "캡션이 2,200자를 넘습니다.",
    9004: "이미지 URL 접근 실패. 핫링크 차단/리디렉션 여부를 확인하세요.",
    190: "액세스 토큰이 만료되었거나 무효화되었습니다. 재발급이 필요합니다.",
}


def _url(path: str) -> str:
    return f"{config.IG_GRAPH_HOST}/{config.IG_API_VERSION}/{path}"


def _request(method: str, path: str, **kwargs) -> dict:
    r = requests.request(method, _url(path), timeout=TIMEOUT, **kwargs)
    try:
        payload = r.json()
    except ValueError:
        r.raise_for_status()
        raise
    if "error" in payload:
        raise InstagramError(payload)
    return payload


def remaining_quota() -> int | None:
    """24시간 게시 한도 잔여분. 숫자를 하드코딩하지 말고 실시간 조회한다."""
    try:
        d = _request("GET", f"{config.IG_USER_ID}/content_publishing_limit",
                     params={"fields": "config,quota_usage",
                             "access_token": config.IG_ACCESS_TOKEN})
        row = (d.get("data") or [{}])[0]
        return row.get("config", {}).get("quota_total", 0) - row.get("quota_usage", 0)
    except Exception as e:                       # noqa: BLE001
        log.warning("게시 한도 조회 실패(계속 진행): %s", e)
        return None


def _create_container(**params) -> str:
    params["access_token"] = config.IG_ACCESS_TOKEN
    d = _request("POST", f"{config.IG_USER_ID}/media", data=params)
    return d["id"]


def _wait_finished(container_id: str) -> None:
    for _ in range(POLL_MAX):
        d = _request("GET", container_id,
                     params={"fields": "status_code,status",
                             "access_token": config.IG_ACCESS_TOKEN})
        code = d.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"컨테이너 처리 실패: {d}")
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"컨테이너 {container_id} 가 제한 시간 내에 준비되지 않았습니다")


def _publish(creation_id: str) -> str:
    d = _request("POST", f"{config.IG_USER_ID}/media_publish",
                 data={"creation_id": creation_id,
                       "access_token": config.IG_ACCESS_TOKEN})
    return d["id"]


def publish_image(image_url: str, caption: str = "") -> str:
    """이미지 1장 게시. 게시된 미디어 ID 를 반환."""
    log.info("컨테이너 생성: %s", image_url)
    cid = _create_container(image_url=image_url, caption=caption[:2200])
    _wait_finished(cid)
    media_id = _publish(cid)
    log.info("게시 완료: media_id=%s", media_id)
    return media_id


def publish_carousel(image_urls: list[str], caption: str = "") -> str:
    """이미지 2~10장 캐러셀 게시. 첫 장의 비율로 전체가 크롭되므로 비율을 통일할 것."""
    if not 2 <= len(image_urls) <= 10:
        raise ValueError("캐러셀은 2~10장이어야 합니다")
    children = []
    for url in image_urls:
        children.append(_create_container(image_url=url, is_carousel_item="true"))
    for cid in children:
        _wait_finished(cid)
    parent = _create_container(media_type="CAROUSEL",
                               children=",".join(children),
                               caption=caption[:2200])
    _wait_finished(parent)
    media_id = _publish(parent)
    log.info("캐러셀 게시 완료: media_id=%s (%d장)", media_id, len(image_urls))
    return media_id


def refresh_long_lived_token() -> dict:
    """장기 토큰(60일) 갱신. 만료 전에 주기적으로 호출해야 자동화가 끊기지 않는다."""
    if config.IG_LOGIN_MODE == "instagram":
        r = requests.get("https://graph.instagram.com/refresh_access_token",
                         params={"grant_type": "ig_refresh_token",
                                 "access_token": config.IG_ACCESS_TOKEN},
                         timeout=TIMEOUT)
    else:
        r = requests.get(f"https://graph.facebook.com/{config.IG_API_VERSION}/oauth/access_token",
                         params={"grant_type": "fb_exchange_token",
                                 "client_id": config.IG_APP_ID,
                                 "client_secret": config.IG_APP_SECRET,
                                 "fb_exchange_token": config.IG_ACCESS_TOKEN},
                         timeout=TIMEOUT)
    payload = r.json()
    if "error" in payload:
        raise InstagramError(payload)
    return payload
