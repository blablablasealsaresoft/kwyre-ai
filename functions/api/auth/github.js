/**
 * Cloudflare Pages Function: GET /api/auth/github
 * Redirects to GitHub OAuth authorization screen with CSRF state.
 */

export async function onRequestGet(context) {
  const { GITHUB_CLIENT_ID, GITHUB_REDIRECT_URI, KV } = context.env;

  if (!GITHUB_CLIENT_ID) {
    return new Response(
      JSON.stringify({ error: 'GITHUB_CLIENT_ID not configured. Set it in Cloudflare Pages → Settings → Environment Variables.' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } },
    );
  }

  const redirectUri = GITHUB_REDIRECT_URI || `${new URL(context.request.url).origin}/api/auth/github/callback`;

  const state = crypto.randomUUID();
  if (KV) {
    await KV.put(`oauth_state:${state}`, '1', { expirationTtl: 300 });
  }

  const params = new URLSearchParams({
    client_id: GITHUB_CLIENT_ID,
    redirect_uri: redirectUri,
    scope: 'read:user user:email',
    state,
  });

  return Response.redirect(
    `https://github.com/login/oauth/authorize?${params}`,
    302,
  );
}
