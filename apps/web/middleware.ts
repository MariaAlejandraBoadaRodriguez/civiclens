import createMiddleware from "next-intl/middleware";
import { routing } from "./i18n/routing";

// Detects the UI language from the cookie or Accept-Language and prefixes routes (/en, /es).
export default createMiddleware(routing);

export const config = {
  matcher: ["/((?!api|_next|_vercel|.*\\..*).*)"],
};
