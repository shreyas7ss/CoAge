import { NextResponse } from "next/server";
export async function POST() {
  const response = NextResponse.json({ ok: true });
  response.cookies.delete("coage_token"); response.cookies.delete("coage_role");
  return response;
}
