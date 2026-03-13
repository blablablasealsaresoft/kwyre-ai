export async function onRequestPost(context) {
  const { request, env } = context;

  const corsHeaders = {
    "Access-Control-Allow-Origin": request.headers.get("Origin") || "https://kwyre.com",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
  };

  try {
    const body = await request.json();
    const { industry, email, company, useCase, budget, timeline } = body;

    if (!industry || !email) {
      return new Response(JSON.stringify({ error: "Industry and email are required" }), {
        status: 400,
        headers: { "Content-Type": "application/json", ...corsHeaders },
      });
    }

    const requestId = crypto.randomUUID();
    const record = {
      id: requestId,
      industry,
      email,
      company: company || "",
      useCase: useCase || "",
      budget: budget || "",
      timeline: timeline || "",
      created_at: new Date().toISOString(),
      status: "pending",
    };

    if (env.KV) {
      await env.KV.put(`custom_request:${requestId}`, JSON.stringify(record));
    }

    return new Response(JSON.stringify({ success: true, requestId }), {
      status: 200,
      headers: { "Content-Type": "application/json", ...corsHeaders },
    });
  } catch (err) {
    return new Response(JSON.stringify({ error: "Invalid request" }), {
      status: 400,
      headers: { "Content-Type": "application/json", ...corsHeaders },
    });
  }
}

export async function onRequestOptions() {
  return new Response(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    },
  });
}
