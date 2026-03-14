export async function onRequestGet(context) {
  const { env } = context;
  const origin = context.request.headers.get('Origin') || '';
  const allowed = ['https://kwyre.com','https://www.kwyre.com','https://mintrail.io','https://www.mintrail.io','https://mintrail.com','https://www.mintrail.com','http://localhost:8788','http://localhost:3000'];
  const corsOrigin = allowed.includes(origin) ? origin : allowed[0];

  return new Response(JSON.stringify({
    publishableKey: env.STRIPE_PUBLISHABLE_KEY || '',
  }), {
    status: 200,
    headers: {
      'Content-Type': 'application/json',
      'Access-Control-Allow-Origin': corsOrigin,
      'Cache-Control': 'public, max-age=3600',
    },
  });
}

export async function onRequestOptions(context) {
  return new Response(null, {
    status: 204,
    headers: {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
    },
  });
}
