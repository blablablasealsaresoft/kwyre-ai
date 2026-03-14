/**
 * Cloudflare Pages Function: GET /api/auth/github/callback
 * Exchanges GitHub OAuth code for tokens, upserts user, issues JWT.
 */

import { generateJWT } from '../../_helpers.js';

export async function onRequestGet(context) {
  const { GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, JWT_SECRET, KV } = context.env;
  const reqUrl = new URL(context.request.url);
  const siteOrigin = reqUrl.origin;
  const code = reqUrl.searchParams.get('code');
  const error = reqUrl.searchParams.get('error');

  if (error || !code) {
    const desc = reqUrl.searchParams.get('error_description') || error || 'unknown';
    return Response.redirect(`${siteOrigin}/login.html?error=oauth_denied&detail=${encodeURIComponent(desc)}`, 302);
  }

  if (!GITHUB_CLIENT_ID || !GITHUB_CLIENT_SECRET) {
    return Response.redirect(`${siteOrigin}/login.html?error=server_error&detail=${encodeURIComponent('GitHub OAuth credentials not configured')}`, 302);
  }

  if (!JWT_SECRET) {
    return Response.redirect(`${siteOrigin}/login.html?error=server_error&detail=${encodeURIComponent('JWT_SECRET not configured')}`, 302);
  }

  // Exchange code for access token
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
      const detail = tokens.error_description || tokens.error || 'No access token returned';
      return Response.redirect(`${siteOrigin}/login.html?error=token_exchange&detail=${encodeURIComponent(detail)}`, 302);
    }
  } catch (err) {
    return Response.redirect(`${siteOrigin}/login.html?error=token_exchange&detail=${encodeURIComponent(err.message)}`, 302);
  }

  // Fetch GitHub user profile
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
    return Response.redirect(`${siteOrigin}/login.html?error=server_error&detail=${encodeURIComponent('Failed to fetch GitHub profile')}`, 302);
  }

  // GitHub may not expose email publicly
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

  // Upsert user in KV
  if (!KV) {
    return Response.redirect(`${siteOrigin}/login.html?error=server_error&detail=${encodeURIComponent('KV namespace not bound')}`, 302);
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
    provider: 'github',
    github_username: ghUser.login,
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
