/**
 * Cloudflare Pages Function: GET /api/auth/google
 * Redirects to Google OAuth consent screen.
 */

export async function onRequestGet(context) {
  const { GOOGLE_CLIENT_ID, GOOGLE_REDIRECT_URI } = context.env;

  if (!GOOGLE_CLIENT_ID) {
    return new Response(
      JSON.stringify({ error: 'GOOGLE_CLIENT_ID not configured. Set it in Cloudflare Pages → Settings → Environment Variables.' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } },
    );
  }

  const redirectUri = GOOGLE_REDIRECT_URI || `${new URL(context.request.url).origin}/api/auth/google/callback`;

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
