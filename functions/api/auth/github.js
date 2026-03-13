/**
 * Cloudflare Pages Function: GET /api/auth/github
 * Redirects to GitHub OAuth authorization screen.
 */

export async function onRequestGet(context) {
  const { GITHUB_CLIENT_ID } = context.env;

  if (!GITHUB_CLIENT_ID) {
    return new Response('GITHUB_CLIENT_ID not configured', { status: 503 });
  }

  const params = new URLSearchParams({
    client_id: GITHUB_CLIENT_ID,
    redirect_uri: 'https://kwyre.com/api/auth/github/callback',
    scope: 'read:user user:email',
  });

  return Response.redirect(
    `https://github.com/login/oauth/authorize?${params}`,
    302,
  );
}
