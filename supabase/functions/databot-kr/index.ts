// 국내 공공 API 중계 (서울 리전)
//
// 왜 필요한가. 해외 GitHub Actions 러너에서 국내 정부 서버는 시간대에 따라
// 통째로 닿지 않는다. 같은 시각 서울에서는 멀쩡히 응답한다 (2026-09-18 00:25 KST,
// kobis.or.kr: 해외에서 연결 실패 / 서울에서 200). 그래서 요청만 서울을 거치게 한다.
//
// 데이터를 여기 저장하지 않는다 — 통과만 시킨다. 저장은 gh-pages 의 cache/ 가 맡는다.
//
// 아무나 쓰는 중계기가 되지 않도록 두 겹으로 막는다.
//   1) 아래 목록에 있는 호스트로만 보낸다
//   2) Supabase 의 JWT 검사를 켜 둔다 (호출 측이 키를 넣어야 한다)

const ALLOWED = new Set([
  "apis.data.go.kr",
  "www.safetydata.go.kr",
  "www.safe182.go.kr",
  "oapi.koreaexim.go.kr",
  "www.kobis.or.kr",
  "kobis.or.kr",
  "www.opinet.co.kr",
]);

const TIMEOUT_MS = 25000;
const MAX_BYTES = 8 * 1024 * 1024;

function fail(status: number, message: string, extra: Record<string, unknown> = {}) {
  return new Response(JSON.stringify({ error: message, ...extra }), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function toBase64(buf: Uint8Array): string {
  // btoa 는 문자열만 받고, 인자를 한 번에 펼치면 스택이 터진다. 조각내서 넘긴다.
  let s = "";
  const CHUNK = 0x8000;
  for (let i = 0; i < buf.length; i += CHUNK) {
    s += String.fromCharCode(...buf.subarray(i, i + CHUNK));
  }
  return btoa(s);
}

Deno.serve(async (req) => {
  if (req.method !== "POST") return fail(405, "POST 만 받습니다");

  let spec: Record<string, unknown>;
  try {
    spec = await req.json();
  } catch {
    return fail(400, "본문이 JSON 이 아닙니다");
  }

  const { url, method = "GET", params, headers, form, body } = spec ?? {};
  if (typeof url !== "string") return fail(400, "url 이 없습니다");

  let target: URL;
  try {
    target = new URL(url);
  } catch {
    return fail(400, "url 형식이 아닙니다");
  }
  if (target.protocol !== "https:") return fail(400, "https 만 허용합니다");
  if (!ALLOWED.has(target.hostname)) {
    return fail(403, "허용되지 않은 호스트입니다: " + target.hostname);
  }

  if (params && typeof params === "object") {
    for (const [k, v] of Object.entries(params as Record<string, unknown>)) {
      if (v !== null && v !== undefined) target.searchParams.set(k, String(v));
    }
  }

  const init: RequestInit = {
    method: String(method).toUpperCase(),
    headers: (headers ?? {}) as Record<string, string>,
  };
  if (form && typeof form === "object") {
    const fd = new URLSearchParams();
    for (const [k, v] of Object.entries(form as Record<string, unknown>)) fd.set(k, String(v));
    init.body = fd;
  } else if (typeof body === "string") {
    init.body = body;
  }

  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), TIMEOUT_MS);
  init.signal = ctl.signal;

  const started = Date.now();
  try {
    const r = await fetch(target.toString(), init);
    const buf = new Uint8Array(await r.arrayBuffer());
    if (buf.byteLength > MAX_BYTES) return fail(502, "응답이 너무 큽니다");
    return new Response(
      JSON.stringify({
        status: r.status,
        content_type: r.headers.get("content-type") ?? "",
        ms: Date.now() - started,
        body_b64: toBase64(buf),
      }),
      { headers: { "content-type": "application/json" } },
    );
  } catch (e) {
    // 서울에서도 못 닿았다는 뜻이다. 호출 측이 직접 연결로 되돌아갈 수 있게
    // 504 로 분명히 알린다.
    return fail(504, String(e).slice(0, 300), { ms: Date.now() - started });
  } finally {
    clearTimeout(timer);
  }
});
