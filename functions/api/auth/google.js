/**
 * Cloudflare Pages Function: GET /api/auth/google
 * Redirects to Google OAuth consent screen with CSRF state + PKCE.
 */

export async function onRequestGet(context) {
  const { GOOGLE_CLIENT_ID, GOOGLE_REDIRECT_URI, KV } = context.env;

  if (!GOOGLE_CLIENT_ID) {
    return new Response(
      JSON.stringify({ error: 'GOOGLE_CLIENT_ID not configured. Set it in Cloudflare Pages → Settings → Environment Variables.' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } },
    );
  }

  const redirectUri = GOOGLE_REDIRECT_URI || `${new URL(context.request.url).origin}/api/auth/google/callback`;

  const state = crypto.randomUUID();
  const codeVerifier = generateCodeVerifier();
  const codeChallenge = await generateCodeChallenge(codeVerifier);

  if (KV) {
    await KV.put(`oauth_state:${state}`, JSON.stringify({ verifier: codeVerifier }), { expirationTtl: 300 });
  }

  const params = new URLSearchParams({
    client_id: GOOGLE_CLIENT_ID,
    redirect_uri: redirectUri,
    response_type: 'code',
    scope: 'openid email profile',
    access_type: 'offline',
    prompt: 'consent',
    state,
    code_challenge: codeChallenge,
    code_challenge_method: 'S256',
  });

  return Response.redirect(
    `https://accounts.google.com/o/oauth2/v2/auth?${params}`,
    302,
  );
}

function generateCodeVerifier() {
  const array = crypto.getRandomValues(new Uint8Array(32));
  return btoa(String.fromCharCode(...array))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

async function generateCodeChallenge(verifier) {
  const encoded = new TextEncoder().encode(verifier);
  const digest = await crypto.subtle.digest('SHA-256', encoded);
  return btoa(String.fromCharCode(...new Uint8Array(digest)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
