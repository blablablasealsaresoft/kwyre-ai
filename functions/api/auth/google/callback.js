/**
 * Cloudflare Pages Function: GET /api/auth/google/callback
 * Exchanges Google OAuth code for tokens, upserts user, issues JWT.
 */

import { generateJWT } from '../../_helpers.js';

export async function onRequestGet(context) {
  const { GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI, JWT_SECRET, KV } = context.env;
  const reqUrl = new URL(context.request.url);
  const siteOrigin = reqUrl.origin;
  const code = reqUrl.searchParams.get('code');
  const error = reqUrl.searchParams.get('error');

  if (error || !code) {
    const desc = reqUrl.searchParams.get('error_description') || error || 'unknown';
    return Response.redirect(`${siteOrigin}/login.html?error=oauth_denied&detail=${encodeURIComponent(desc)}`, 302);
  }

  if (!GOOGLE_CLIENT_ID || !GOOGLE_CLIENT_SECRET) {
    return Response.redirect(`${siteOrigin}/login.html?error=server_error&detail=${encodeURIComponent('Google OAuth credentials not configured')}`, 302);
  }

  if (!JWT_SECRET) {
    return Response.redirect(`${siteOrigin}/login.html?error=server_error&detail=${encodeURIComponent('JWT_SECRET not configured')}`, 302);
  }

  const redirectUri = GOOGLE_REDIRECT_URI || `${siteOrigin}/api/auth/google/callback`;

  // Exchange code for tokens
  let tokens;
  try {
    const tokenRes = await fetch('https://oauth2.googleapis.com/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        code,
        client_id: GOOGLE_CLIENT_ID,
        client_secret: GOOGLE_CLIENT_SECRET,
        redirect_uri: redirectUri,
        grant_type: 'authorization_code',
      }),
    });

    tokens = await tokenRes.json();
    if (!tokenRes.ok || !tokens.access_token) {
      const detail = tokens.error_description || tokens.error || `HTTP ${tokenRes.status}`;
      return Response.redirect(`${siteOrigin}/login.html?error=token_exchange&detail=${encodeURIComponent(detail)}`, 302);
    }
  } catch (err) {
    return Response.redirect(`${siteOrigin}/login.html?error=token_exchange&detail=${encodeURIComponent(err.message)}`, 302);
  }

  // Fetch user profile
  let profile;
  try {
    const profileRes = await fetch('https://www.googleapis.com/oauth2/v2/userinfo', {
      headers: { Authorization: `Bearer ${tokens.access_token}` },
    });
    profile = await profileRes.json();
  } catch (err) {
    return Response.redirect(`${siteOrigin}/login.html?error=server_error&detail=${encodeURIComponent('Failed to fetch profile: ' + err.message)}`, 302);
  }

  if (!profile.email) {
    return Response.redirect(`${siteOrigin}/login.html?error=no_email`, 302);
  }

  // Upsert user in KV
  if (!KV) {
    return Response.redirect(`${siteOrigin}/login.html?error=server_error&detail=${encodeURIComponent('KV namespace not bound')}`, 302);
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
    provider: 'google',
    created_at: existing?.created_at || new Date().toISOString(),
    updated_at: new Date().toISOString(),
    licenses: existing?.licenses || [],
    addons: existing?.addons || [],
    stripe_customer_id: existing?.stripe_customer_id || null,
  };
  await KV.put(kvKey, JSON.stringify(user));

  // Issue JWT (24h)
  const jwt = await generateJWT(
    { email: user.email, name: user.name, picture: user.picture },
    JWT_SECRET,
    86400,
  );

  return Response.redirect(
    `${siteOrigin}/login.html?token=${encodeURIComponent(jwt)}`,
    302,
  );
}
