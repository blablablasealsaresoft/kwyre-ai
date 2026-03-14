/**
 * Kwyre Cloud API Proxy
 *
 * Cloudflare Worker that proxies authenticated requests from api.kwyre.com
 * to the upstream H100 inference server. Handles CORS, JWT auth for cloud
 * users, API key passthrough for local keys, and SSE streaming.
 */

const ALLOWED_ORIGINS = [
  'https://kwyre.com',
  'https://www.kwyre.com',
  'http://localhost:8000',
  'http://127.0.0.1:8000',
];

const ALLOWED_PATHS = [
  '/v1/chat/completions',
  '/v1/session/end',
  '/v1/documents/upload',
  '/v1/adapter/list',
  '/v1/adapter/load',
  '/v1/adapter/unload',
  '/v1/adapter/status',
  '/v1/adapter/check-update',
  '/v1/analytics/predict',
  '/v1/analytics/risk',
  '/v1/models',
  '/health',
];

function corsHeaders(origin) {
  const allowed = ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0];
  return {
    'Access-Control-Allow-Origin': allowed,
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    'Access-Control-Max-Age': '86400',
  };
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = request.headers.get('Origin') || '';
    const cors = corsHeaders(origin);

    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: cors });
    }

    const path = url.pathname;
    if (!ALLOWED_PATHS.some(p => path === p || path.startsWith(p + '/'))) {
      return Response.json({ error: 'Not found' }, { status: 404, headers: cors });
    }

    const auth = request.headers.get('Authorization') || '';
    if (!auth.startsWith('Bearer ')) {
      return Response.json({ error: 'Missing Authorization' }, { status: 401, headers: cors });
    }

    const token = auth.slice(7);
    let upstreamKey = env.UPSTREAM_API_KEY || 'sk-kwyre-cloud-proxy';

    if (token.startsWith('sk-kwyre-')) {
      upstreamKey = token;
    } else if (env.JWT_SECRET) {
      try {
        await verifyJWT(token, env.JWT_SECRET);
      } catch (e) {
        return Response.json({ error: e.message }, { status: 401, headers: cors });
      }
    }

    if (!env.UPSTREAM_URL) {
      return Response.json({ error: 'UPSTREAM_URL not configured' }, { status: 503, headers: cors });
    }
    const upstream = env.UPSTREAM_URL + path + url.search;
    const headers = new Headers(request.headers);
    headers.set('Authorization', 'Bearer ' + upstreamKey);
    headers.delete('Host');

    try {
      const res = await fetch(upstream, {
        method: request.method,
        headers,
        body: request.method !== 'GET' && request.method !== 'HEAD' ? request.body : undefined,
      });

      const respHeaders = new Headers(res.headers);
      for (const [k, v] of Object.entries(cors)) respHeaders.set(k, v);
      respHeaders.set('X-Content-Type-Options', 'nosniff');
      respHeaders.set('X-Frame-Options', 'DENY');

      return new Response(res.body, { status: res.status, headers: respHeaders });
    } catch (e) {
      return Response.json({ error: 'Upstream unavailable' }, { status: 502, headers: cors });
    }
  },
};

async function verifyJWT(token, secret) {
  const [h, p, s] = token.split('.');
  if (!h || !p || !s) throw new Error('Malformed JWT');
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey('raw', enc.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['verify']);
  const sig = Uint8Array.from(atob(s.replace(/-/g, '+').replace(/_/g, '/')), c => c.charCodeAt(0));
  if (!await crypto.subtle.verify('HMAC', key, sig, enc.encode(h + '.' + p))) throw new Error('Bad signature');
  const claims = JSON.parse(atob(p.replace(/-/g, '+').replace(/_/g, '/')));
  if (claims.exp && claims.exp < Date.now() / 1000) throw new Error('Expired');
  return claims;
}
