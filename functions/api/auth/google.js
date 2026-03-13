/**
 * Cloudflare Pages Function: GET /api/auth/google
 * Redirects to Google OAuth consent screen.
 */

export async function onRequestGet(context) {
  const { GOOGLE_CLIENT_ID, GOOGLE_REDIRECT_URI } = context.env;

  if (!GOOGLE_CLIENT_ID) {
    return new Response('GOOGLE_CLIENT_ID not configured', { status: 503 });
  }

  const redirectUri = GOOGLE_REDIRECT_URI || 'https://kwyre.com/api/auth/google/callback';

  const params = new URLSearchParams({
    client_id: GOOGLE_CLIENT_ID,
    redirect_uri: redirectUri,
    response_type: 'code',
    scope: 'openid email profile',
    access_type: 'offline',
    prompt: 'consent',
  });

  return Response.redirect(
    `https://accounts.google.com/o/oauth2/v2/auth?${params}`,
    302,
  );
}
