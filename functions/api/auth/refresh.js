/**
 * Cloudflare Pages Function: POST /api/auth/refresh
 * Issues a new access token from a valid refresh token cookie.
 */

import { verifyJWT, generateJWT, extractCookie, corsHeaders, jsonResponse, optionsResponse } from '../_helpers.js';

export async function onRequestOptions(context) {
  return optionsResponse(context.request.headers.get('Origin'));
}

export async function onRequestPost(context) {
  const { JWT_SECRET, KV } = context.env;
  const origin = context.request.headers.get('Origin');

  const refreshToken = extractCookie(context.request, 'kwyre_refresh');
  if (!refreshToken) {
    return jsonResponse({ error: 'No refresh token' }, 401, origin);
  }

  let claims;
  try {
    claims = await verifyJWT(refreshToken, JWT_SECRET);
  } catch (err) {
    return jsonResponse({ error: 'Invalid refresh token' }, 401, origin);
  }

  if (claims.type !== 'refresh') {
    return jsonResponse({ error: 'Invalid token type' }, 401, origin);
  }

  const user = await KV.get(`user:${claims.email}`, 'json');
  if (!user) {
    return jsonResponse({ error: 'User not found' }, 404, origin);
  }

  const accessToken = await generateJWT(
    { email: user.email, name: user.name, picture: user.picture },
    JWT_SECRET,
    3600,
  );

  const cors = corsHeaders(origin);
  const headers = new Headers({
    'Content-Type': 'application/json',
    ...cors,
    'Access-Control-Allow-Credentials': 'true',
  });
  headers.append('Set-Cookie', `kwyre_token=${accessToken}; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=3600`);

  return new Response(JSON.stringify({ ok: true }), { status: 200, headers });
}
