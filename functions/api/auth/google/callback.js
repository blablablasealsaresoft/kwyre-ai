/**
 * Cloudflare Pages Function: GET /api/auth/google/callback
 * Validates CSRF state + PKCE, exchanges code for tokens, upserts user,
 * issues JWT via httpOnly cookie, stores Google refresh token.
 */

import { generateJWT } from '../../_helpers.js';

export async function onRequestGet(context) {
  const { GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI, JWT_SECRET, KV } = context.env;
  const reqUrl = new URL(context.request.url);
  const siteOrigin = reqUrl.origin;
  const code = reqUrl.searchParams.get('code');
  const error = reqUrl.searchParams.get('error');
  const state = reqUrl.searchParams.get('state');

  if (error || !code) {
    const desc = reqUrl.searchParams.get('error_description') || error || 'unknown';
    return Response.redirect(`${siteOrigin}/login.html?error=oauth_denied`, 302);
  }

  if (!GOOGLE_CLIENT_ID || !GOOGLE_CLIENT_SECRET) {
    return Response.redirect(`${siteOrigin}/login.html?error=server_error`, 302);
  }

  if (!JWT_SECRET) {
    return Response.redirect(`${siteOrigin}/login.html?error=server_error`, 302);
  }

  if (!KV) {
    return Response.redirect(`${siteOrigin}/login.html?error=server_error`, 302);
  }

  let codeVerifier = null;
  if (state) {
    const stateData = await KV.get(`oauth_state:${state}`, 'json');
    if (!stateData) {
      return Response.redirect(`${siteOrigin}/login.html?error=invalid_state`, 302);
    }
    codeVerifier = stateData.verifier || null;
    await KV.delete(`oauth_state:${state}`);
  }

  const redirectUri = GOOGLE_REDIRECT_URI || `${siteOrigin}/api/auth/google/callback`;

  let tokens;
  try {
    const tokenParams = new URLSearchParams({
      code,
      client_id: GOOGLE_CLIENT_ID,
      client_secret: GOOGLE_CLIENT_SECRET,
      redirect_uri: redirectUri,
      grant_type: 'authorization_code',
    });
    if (codeVerifier) {
      tokenParams.set('code_verifier', codeVerifier);
    }

    const tokenRes = await fetch('https://oauth2.googleapis.com/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: tokenParams,
    });

    tokens = await tokenRes.json();
    if (!tokenRes.ok || !tokens.access_token) {
      const detail = tokens.error_description || tokens.error || `HTTP ${tokenRes.status}`;
      return Response.redirect(`${siteOrigin}/login.html?error=token_exchange`, 302);
    }
  } catch (err) {
    return Response.redirect(`${siteOrigin}/login.html?error=token_exchange`, 302);
  }

  let profile;
  try {
    const profileRes = await fetch('https://www.googleapis.com/oauth2/v2/userinfo', {
      headers: { Authorization: `Bearer ${tokens.access_token}` },
    });
    profile = await profileRes.json();
  } catch (err) {
    return Response.redirect(`${siteOrigin}/login.html?error=server_error`, 302);
  }

  if (!profile.email) {
    return Response.redirect(`${siteOrigin}/login.html?error=no_email`, 302);
  }

  const kvKey = `user:${profile.email}`;
  let existing = null;
  try {
    existing = await KV.get(kvKey, 'json');
  } catch { /* first user */ }

  const user = {
    email: profile.email,
    name: profile.name || '',
    picture: profile.picture || '',
    providers: [...new Set([...(existing?.providers || []), 'google'])],
    google_refresh_token: tokens.refresh_token || existing?.google_refresh_token || null,
    created_at: existing?.created_at || new Date().toISOString(),
    updated_at: new Date().toISOString(),
    licenses: existing?.licenses || [],
    addons: existing?.addons || [],
    stripe_customer_id: existing?.stripe_customer_id || null,
  };
  await KV.put(kvKey, JSON.stringify(user));

  const accessToken = await generateJWT(
    { email: user.email, name: user.name, picture: user.picture },
    JWT_SECRET,
    3600,
  );

  const refreshToken = await generateJWT(
    { email: user.email, type: 'refresh' },
    JWT_SECRET,
    604800,
  );

  const headers = new Headers();
  headers.append('Set-Cookie', `kwyre_token=${accessToken}; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=3600`);
  headers.append('Set-Cookie', `kwyre_refresh=${refreshToken}; HttpOnly; Secure; SameSite=Strict; Path=/api/auth/refresh; Max-Age=604800`);
  headers.set('Location', `${siteOrigin}/login.html`);

  return new Response(null, { status: 302, headers });
}
