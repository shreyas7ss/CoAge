import { NextRequest, NextResponse } from "next/server";

export function middleware(request: NextRequest) {
  const role = request.cookies.get("coage_role")?.value;
  const token = request.cookies.get("coage_token")?.value;
  const path = request.nextUrl.pathname;
  if (path === "/login" && token) return NextResponse.redirect(new URL(role === "faculty" ? "/faculty" : "/student", request.url));
  if (path.startsWith("/student") || path.startsWith("/faculty")) {
    if (!token) return NextResponse.redirect(new URL("/login", request.url));
    if (role && !path.startsWith(`/${role}`)) return NextResponse.redirect(new URL(`/${role}`, request.url));
  }
  return NextResponse.next();
}
export const config = { matcher: ["/login", "/student/:path*", "/faculty/:path*"] };
