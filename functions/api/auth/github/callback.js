/**
 * Cloudflare Pages Function: GET /api/auth/github/callback
 * Validates CSRF state, exchanges code for tokens, upserts user,
 * issues JWT via httpOnly cookie.
 */

import { generateJWT } from '../../_helpers.js';

export async function onRequestGet(context) {
  const { GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, JWT_SECRET, KV } = context.env;
  const reqUrl = new URL(context.request.url);
  const siteOrigin = reqUrl.origin;
  const code = reqUrl.searchParams.get('code');
  const error = reqUrl.searchParams.get('error');
  const state = reqUrl.searchParams.get('state');

  if (error || !code) {
    return Response.redirect(`${siteOrigin}/login.html?error=oauth_denied`, 302);
  }

  if (!GITHUB_CLIENT_ID || !GITHUB_CLIENT_SECRET) {
    return Response.redirect(`${siteOrigin}/login.html?error=server_error`, 302);
  }

  if (!JWT_SECRET) {
    return Response.redirect(`${siteOrigin}/login.html?error=server_error`, 302);
  }

  if (!KV) {
    return Response.redirect(`${siteOrigin}/login.html?error=server_error`, 302);
  }

  if (state) {
    const stateValid = await KV.get(`oauth_state:${state}`, 'text');
    if (!stateValid) {
      return Response.redirect(`${siteOrigin}/login.html?error=invalid_state`, 302);
    }
    await KV.delete(`oauth_state:${state}`);
  }

  let tokens;
  try {
    const tokenRes = await fetch('https://github.com/login/oauth/access_token', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify({
        client_id: GITHUB_CLIENT_ID,
        client_secret: GITHUB_CLIENT_SECRET,
        code,
      }),
    });

    tokens = await tokenRes.json();
    if (!tokens.access_token) {
      return Response.redirect(`${siteOrigin}/login.html?error=token_exchange`, 302);
    }
  } catch (err) {
    return Response.redirect(`${siteOrigin}/login.html?error=token_exchange`, 302);
  }

  let ghUser;
  try {
    const userRes = await fetch('https://api.github.com/user', {
      headers: {
        Authorization: `Bearer ${tokens.access_token}`,
        'User-Agent': 'Kwyre-Auth',
      },
    });
    ghUser = await userRes.json();
  } catch (err) {
    return Response.redirect(`${siteOrigin}/login.html?error=server_error`, 302);
  }

  let email = ghUser.email;
  if (!email) {
    try {
      const emailRes = await fetch('https://api.github.com/user/emails', {
        headers: {
          Authorization: `Bearer ${tokens.access_token}`,
          'User-Agent': 'Kwyre-Auth',
        },
      });
      const emails = await emailRes.json();
      const primary = emails.find((e) => e.primary && e.verified);
      email = primary?.email || emails[0]?.email;
    } catch { /* fallthrough */ }
  }

  if (!email) {
    return Response.redirect(`${siteOrigin}/login.html?error=no_email`, 302);
  }

  const kvKey = `user:${email}`;
  let existing = null;
  try {
    existing = await KV.get(kvKey, 'json');
  } catch { /* first user */ }

  const user = {
    email,
    name: ghUser.name || ghUser.login || '',
    picture: ghUser.avatar_url || '',
    providers: [...new Set([...(existing?.providers || []), 'github'])],
    github_username: ghUser.login,
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
