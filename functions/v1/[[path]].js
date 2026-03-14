/**
 * Cloudflare Pages Function: /v1/*
 * Proxies inference API requests to the upstream H100 GPU server.
 */

import { corsHeaders } from '../api/_helpers.js';

export async function onRequest(context) {
  const upstreamBase = context.env.UPSTREAM_URL;
  if (!upstreamBase) {
    return Response.json({ error: 'UPSTREAM_URL not configured' }, { status: 503 });
  }

  const url = new URL(context.request.url);
  const origin = context.request.headers.get('Origin') || '';
  const upstream = upstreamBase + url.pathname + url.search;

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
    const cors = corsHeaders(origin);
    for (const [k, v] of Object.entries(cors)) respHeaders.set(k, v);
    respHeaders.set('X-Content-Type-Options', 'nosniff');
    respHeaders.set('X-Frame-Options', 'DENY');

    return new Response(res.body, { status: res.status, headers: respHeaders });
  } catch (e) {
    return Response.json({ error: 'Upstream unavailable' }, { status: 502 });
  }
}
