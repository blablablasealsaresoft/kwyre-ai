/**
 * Cloudflare Pages Function: GET /api/auth/github/callback
 * Exchanges GitHub OAuth code for tokens, upserts user, issues JWT.
 */

import { generateJWT } from '../../_helpers.js';

export async function onRequestGet(context) {
  const { GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, JWT_SECRET, KV } = context.env;
  const url = new URL(context.request.url);
  const code = url.searchParams.get('code');
  const error = url.searchParams.get('error');

  if (error || !code) {
    return Response.redirect('https://kwyre.com/login.html?error=oauth_denied', 302);
  }

  // Exchange code for access token
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

  const tokens = await tokenRes.json();
  if (!tokens.access_token) {
    return Response.redirect('https://kwyre.com/login.html?error=token_exchange', 302);
  }

  // Fetch GitHub user profile
  const userRes = await fetch('https://api.github.com/user', {
    headers: {
      Authorization: `Bearer ${tokens.access_token}`,
      'User-Agent': 'Kwyre-Auth',
    },
  });
  const ghUser = await userRes.json();

  // GitHub may not expose email publicly — fetch from /user/emails
  let email = ghUser.email;
  if (!email) {
    const emailRes = await fetch('https://api.github.com/user/emails', {
      headers: {
        Authorization: `Bearer ${tokens.access_token}`,
        'User-Agent': 'Kwyre-Auth',
      },
    });
    const emails = await emailRes.json();
    const primary = emails.find((e) => e.primary && e.verified);
    email = primary?.email || emails[0]?.email;
  }

  if (!email) {
    return Response.redirect('https://kwyre.com/login.html?error=no_email', 302);
  }

  // Upsert user in KV
  const kvKey = `user:${email}`;
  const existing = await KV.get(kvKey, 'json');
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
