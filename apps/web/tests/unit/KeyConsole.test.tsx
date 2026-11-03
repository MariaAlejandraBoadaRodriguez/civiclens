import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { KeyConsole } from "@/components/admin/KeyConsole";
import type { ApiKey } from "@/lib/api-types";
import { json, renderIn } from "./render";

const existing: ApiKey = {
  id: "k1",
  name: "Ministerio de Hacienda",
  prefix: "cl_live_ab12cd34",
  scopes: ["reports:read"],
  created_at: "2026-10-01T12:00:00+00:00",
  last_used_at: null,
  revoked_at: null,
};

describe("KeyConsole", () => {
  it("creates a key, shows it once and sends the chosen scopes to this app (not the API)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      json({ ...existing, id: "k2", name: "Data team", scopes: ["reports:read", "models:run"], key: "cl_live_x.secret" }, 201),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderIn("en", <KeyConsole initial={[existing]} />);
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Data team" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /Run models/ }));
    fireEvent.click(screen.getByRole("button", { name: "Create key" }));
    expect(await screen.findByLabelText("New API key")).toHaveValue("cl_live_x.secret");
    expect(screen.getByText("Copy the key now")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/admin/keys");
    expect(JSON.parse(init.body)).toEqual({ name: "Data team", scopes: ["models:run", "reports:read"] });
    expect(screen.getAllByTestId("api-key-row")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "I have stored it" }));
    expect(screen.queryByLabelText("New API key")).toBeNull(); // never shown again
  });

  it("revokes only after confirmation, in Spanish", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    renderIn("es", <KeyConsole initial={[existing]} />);
    fireEvent.click(screen.getByRole("button", { name: "Revocar la clave Ministerio de Hacienda" }));
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Confirmar: revocar ahora" }));
    await waitFor(() => expect(screen.getByText("Revocada")).toBeInTheDocument());
    expect(fetchMock.mock.calls[0][0]).toBe("/api/admin/keys/k1");
    expect(fetchMock.mock.calls[0][1].method).toBe("DELETE");
  });

  it("shows the localized problem when the session ended", async () => {
    const problem = { type: "about:blank", status: 401, code: "auth.admin_required", title: "Tu sesión de administración terminó" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(problem, 401)));
    renderIn("es", <KeyConsole initial={[]} />);
    expect(screen.getByText("Aún no hay claves. Crea la primera arriba.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Nombre"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Crear clave" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Tu sesión de administración terminó");
  });

  it("cannot create a key without a name or a scope", () => {
    renderIn("en", <KeyConsole initial={[]} />);
    expect(screen.getByRole("button", { name: "Create key" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /Read executive reports/ }));
    expect(screen.getByRole("button", { name: "Create key" })).toBeDisabled();
  });
});
