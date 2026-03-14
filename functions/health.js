/**
 * Cloudflare Pages Function: /health
 * Proxies health check to the upstream H100 GPU server.
 */

const UPSTREAM = 'http://165.227.47.89:8080';

export async function onRequestGet(context) {
  try {
    const res = await fetch(UPSTREAM + '/health', {
      headers: context.request.headers,
    });
    const respHeaders = new Headers(res.headers);
    respHeaders.set('Access-Control-Allow-Origin', '*');
    return new Response(res.body, { status: res.status, headers: respHeaders });
  } catch (e) {
    return Response.json({ error: 'Upstream unavailable: ' + e.message }, { status: 502 });
  }
}
