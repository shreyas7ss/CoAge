import { NextResponse } from "next/server";

const backend = process.env.BACKEND_API_URL ?? "http://localhost:8000/api/v1";
export async function POST(request: Request) {
  const payload = await request.json();
  const result = await fetch(`${backend}/auth/login`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload), cache: "no-store",
  });
  const body = await result.json().catch(() => ({}));
  if (!result.ok) return NextResponse.json(body, { status: result.status });
  const response = NextResponse.json({ user: body.user });
  const secure = process.env.NODE_ENV === "production";
  response.cookies.set("coage_token", body.access_token, { httpOnly: true, sameSite: "lax", secure, path: "/", maxAge: 60 * 60 * 8 });
  response.cookies.set("coage_role", body.role, { httpOnly: true, sameSite: "lax", secure, path: "/", maxAge: 60 * 60 * 8 });
  return response;
}
