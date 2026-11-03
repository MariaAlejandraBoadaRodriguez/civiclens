import { forwardToApi } from "@/lib/admin/proxy";

export const dynamic = "force-dynamic";

export function GET(request: Request) {
  return forwardToApi(request, "/api/v1/keys", "GET");
}

export function POST(request: Request) {
  return forwardToApi(request, "/api/v1/keys", "POST");
}
