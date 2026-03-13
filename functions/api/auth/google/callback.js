/**
 * Cloudflare Pages Function: GET /api/auth/google/callback
 * Exchanges Google OAuth code for tokens, upserts user, issues JWT.
 */

import { generateJWT } from '../../_helpers.js';

export async function onRequestGet(context) {
  const { GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI, JWT_SECRET, KV } = context.env;
  const url = new URL(context.request.url);
  const code = url.searchParams.get('code');
  const error = url.searchParams.get('error');

  if (error || !code) {
    return Response.redirect('https://kwyre.com/login.html?error=oauth_denied', 302);
  }

  const redirectUri = GOOGLE_REDIRECT_URI || 'https://kwyre.com/api/auth/google/callback';

  // Exchange code for tokens
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

  const tokens = await tokenRes.json();
  if (!tokenRes.ok || !tokens.access_token) {
    return Response.redirect('https://kwyre.com/login.html?error=token_exchange', 302);
  }

  // Fetch user profile
  const profileRes = await fetch('https://www.googleapis.com/oauth2/v2/userinfo', {
    headers: { Authorization: `Bearer ${tokens.access_token}` },
  });
  const profile = await profileRes.json();

  if (!profile.email) {
    return Response.redirect('https://kwyre.com/login.html?error=no_email', 302);
  }

  // Upsert user in KV
  const kvKey = `user:${profile.email}`;
  const existing = await KV.get(kvKey, 'json');
  const user = {
    email: profile.email,
    name: profile.name || '',
    picture: profile.picture || '',
    provider: 'google',
    created_at: existing?.created_at || new Date().toISOString(),
    updated_at: new Date().toISOString(),
    licenses: existing?.licenses || [],
    addons: existing?.addons || [],
  };
  await KV.put(kvKey, JSON.stringify(user));

  // Issue JWT (24h)
  const jwt = await generateJWT(
    { email: user.email, name: user.name, picture: user.picture },
    JWT_SECRET,
    86400,
  );

  return Response.redirect(
    `https://kwyre.com/dashboard.html?token=${encodeURIComponent(jwt)}`,
    302,
  );
}
