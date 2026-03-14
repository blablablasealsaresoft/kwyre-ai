/**
 * Cloudflare Pages Function: /health
 * Proxies health check to the upstream H100 GPU server.
 */

import { corsHeaders } from './api/_helpers.js';

export async function onRequestGet(context) {
  const upstreamBase = context.env.UPSTREAM_URL;
  if (!upstreamBase) {
    return Response.json({ error: 'UPSTREAM_URL not configured' }, { status: 503 });
  }

  const origin = context.request.headers.get('Origin') || '';

  try {
    const res = await fetch(upstreamBase + '/health', {
      headers: context.request.headers,
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
