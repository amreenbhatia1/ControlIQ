import { NextResponse, type NextRequest } from "next/server";

const SESSION_COOKIE = "controliq_session";

// Coarse routing guard only. Every API call is authorised server-side by the backend.
export function middleware(req: NextRequest) {
  const { pathname, search } = req.nextUrl;
  // /login stays reachable even with a cookie: the server-side session may have expired.
  if (pathname === "/login") return NextResponse.next();
  if (!req.cookies.has(SESSION_COOKIE)) {
    const url = new URL("/login", req.url);
    if (pathname !== "/") url.searchParams.set("next", pathname + search);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
