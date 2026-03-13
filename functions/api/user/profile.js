/**
 * Cloudflare Pages Function: GET /api/user/profile
 * Returns authenticated user's profile from KV.
 */

import { verifyJWT, extractBearer, jsonResponse, optionsResponse } from '../_helpers.js';

export async function onRequestOptions(context) {
  return optionsResponse(context.request.headers.get('Origin'));
}

export async function onRequestGet(context) {
  const { JWT_SECRET, KV } = context.env;
  const origin = context.request.headers.get('Origin');

  const token = extractBearer(context.request);
  if (!token) {
    return jsonResponse({ error: 'Missing Authorization header' }, 401, origin);
  }

  let claims;
  try {
    claims = await verifyJWT(token, JWT_SECRET);
  } catch (err) {
    return jsonResponse({ error: err.message }, 401, origin);
  }

  const user = await KV.get(`user:${claims.email}`, 'json');
  if (!user) {
    return jsonResponse({ error: 'User not found' }, 404, origin);
  }

  return jsonResponse({
    email: user.email,
    name: user.name,
    picture: user.picture,
    created_at: user.created_at,
    licenses: user.licenses,
    addons: user.addons,
  }, 200, origin);
}
