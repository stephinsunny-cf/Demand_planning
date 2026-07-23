import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

export function middleware(req: NextRequest) {
  const token = req.cookies.get('sb-token')?.value || req.headers.get('authorization');
  const pathname = req.nextUrl.pathname;

  // Allow public assets, login, and reset-password page
  if (
    pathname.startsWith('/login') ||
    pathname.startsWith('/reset-password') ||
    pathname.startsWith('/_next') ||
    pathname.startsWith('/favicon.ico') ||
    pathname.startsWith('/api')
  ) {
    return NextResponse.next();
  }

  // If DEMO_MODE is active or token exists, proceed
  if (process.env.NEXT_PUBLIC_DEMO_MODE === 'true' || token) {
    return NextResponse.next();
  }

  // Redirect to login if unauthenticated
  const loginUrl = new URL('/login', req.url);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
};
