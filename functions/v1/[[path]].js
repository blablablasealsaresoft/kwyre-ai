/**
 * Cloudflare Pages Function: /v1/*
 * Proxies inference API requests to the upstream H100 GPU server.
 */

const UPSTREAM = 'http://165.227.47.89:8080';

export async function onRequest(context) {
  const url = new URL(context.request.url);
  const upstream = UPSTREAM + url.pathname + url.search;

  const headers = new Headers(context.request.headers);
  headers.delete('Host');

  try {
    const res = await fetch(upstream, {
      method: context.request.method,
      headers,
      body: context.request.method !== 'GET' && context.request.method !== 'HEAD'
        ? context.request.body : undefined,
    });

    const respHeaders = new Headers(res.headers);
    respHeaders.set('Access-Control-Allow-Origin', url.origin);
    respHeaders.set('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    respHeaders.set('Access-Control-Allow-Headers', 'Content-Type, Authorization');

    return new Response(res.body, { status: res.status, headers: respHeaders });
  } catch (e) {
    return Response.json({ error: 'Upstream unavailable: ' + e.message }, { status: 502 });
  }
}
