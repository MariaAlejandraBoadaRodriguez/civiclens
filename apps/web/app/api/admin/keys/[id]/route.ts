import { forwardToApi } from "@/lib/admin/proxy";

export const dynamic = "force-dynamic";

export function DELETE(request: Request, { params }: { params: { id: string } }) {
  return forwardToApi(request, `/api/v1/keys/${encodeURIComponent(params.id)}`, "DELETE");
}
