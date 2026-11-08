import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

const backend = process.env.BACKEND_API_URL ?? "http://localhost:8000/api/v1";
async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const cookieStore = await cookies();
  const token = cookieStore.get("coage_token")?.value;
  if (!token) return NextResponse.json({ detail: "Sign in to continue." }, { status: 401 });
  const { path } = await context.params;
  const target = `${backend}/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`;
  const headers = new Headers(request.headers);
  headers.delete("host"); headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(target, {
    method: request.method, headers,
    body: ["GET", "HEAD"].includes(request.method) ? undefined : await request.arrayBuffer(),
    cache: "no-store",
  });
  const data = await response.arrayBuffer();
  return new NextResponse(data, { status: response.status, headers: { "Content-Type": response.headers.get("Content-Type") ?? "application/json" } });
}
export { proxy as GET, proxy as POST, proxy as PUT, proxy as PATCH, proxy as DELETE };
