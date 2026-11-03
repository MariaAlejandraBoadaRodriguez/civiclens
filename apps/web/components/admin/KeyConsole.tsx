"use client";

import { useState, type FormEvent } from "react";
import { useLocale, useTranslations } from "next-intl";
import { ApiErrorNotice } from "@/components/ui/ApiErrorNotice";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { API_SCOPES, type ApiKey, type ApiScope, type CreatedApiKey } from "@/lib/api-types";
import { apiRequest, type ApiFailure } from "@/lib/apiClient";
import { cn } from "@/lib/cn";
import { formatDate } from "@/lib/format";

/** Issue, list and revoke agency API keys. Calls this app's /api/admin routes (same origin). */
export function KeyConsole({ initial }: { initial: ApiKey[] }) {
  const t = useTranslations("admin");
  const locale = useLocale();
  const [keys, setKeys] = useState<ApiKey[]>(initial);
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState<Set<ApiScope>>(new Set(["reports:read"]));
  const [created, setCreated] = useState<CreatedApiKey | null>(null);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiFailure | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);

  const toggleScope = (scope: ApiScope) =>
    setScopes((prev) => {
      const next = new Set(prev);
      if (next.has(scope)) next.delete(scope);
      else next.add(scope);
      return next;
    });

  async function create(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    const res = await apiRequest<CreatedApiKey>("/api/admin/keys", {
      locale,
      base: "",
      json: { name: name.trim(), scopes: API_SCOPES.filter((s) => scopes.has(s)) },
    });
    setBusy(false);
    if (!res.ok) return setError(res.error);
    setError(null);
    setCreated(res.data);
    setCopied(false);
    setName("");
    const { key: _secret, ...listed } = res.data;
    setKeys((prev) => [listed, ...prev]);
  }

  async function revoke(id: string) {
    const res = await apiRequest<null>(`/api/admin/keys/${encodeURIComponent(id)}`, {
      locale,
      base: "",
      method: "DELETE",
    });
    setConfirming(null);
    if (!res.ok) return setError(res.error);
    setError(null);
    const now = new Date().toISOString();
    setKeys((prev) => prev.map((k) => (k.id === id ? { ...k, revoked_at: k.revoked_at ?? now } : k)));
  }

  async function copy(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
    } catch {
      setCopied(false); // the key stays selectable in the field
    }
  }

  const canCreate = name.trim().length > 0 && scopes.size > 0 && !busy;

  return (
    <div className="flex flex-col gap-5">
      {error && <ApiErrorNotice error={error} />}
      {created && (
        <Card tone="attention" title={t("created.title")} titleId="created-key" aria-live="polite">
          <p className="m-0 text-[15px]">{t("created.body", { name: created.name })}</p>
          <div className="flex flex-wrap items-center gap-2">
            <label htmlFor="new-key" className="sr-only">
              {t("created.label")}
            </label>
            <input
              id="new-key"
              readOnly
              value={created.key}
              onFocus={(e) => e.currentTarget.select()}
              className="min-w-0 flex-1 rounded-control border border-flag-border bg-surface px-3 py-2.5 font-mono text-sm text-ink"
            />
            <Button variant="attention" onClick={() => void copy(created.key)}>
              {copied ? t("created.copied") : t("created.copy")}
            </Button>
          </div>
          <Button variant="ghost" className="self-start" onClick={() => setCreated(null)}>
            {t("created.done")}
          </Button>
        </Card>
      )}

      <Card title={t("form.title")} titleId="new-key-form">
        <form onSubmit={(e) => void create(e)} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="key-name" className="text-sm font-medium text-ink">
              {t("form.name")}
            </label>
            <input
              id="key-name"
              value={name}
              maxLength={120}
              onChange={(e) => setName(e.target.value)}
              aria-describedby="key-name-hint"
              className="rounded-control border border-line-strong bg-surface px-3 py-2.5 text-[15px] text-ink"
            />
            <span id="key-name-hint" className="text-[13px] text-muted">
              {t("form.nameHint")}
            </span>
          </div>
          <fieldset className="m-0 flex flex-col gap-2 border-0 p-0">
            <legend className="mb-1 text-sm font-medium text-ink">{t("form.scopes")}</legend>
            {API_SCOPES.map((scope) => (
              <label key={scope} className="flex min-h-touch items-start gap-3 text-[15px]">
                <input
                  type="checkbox"
                  className="mt-1 h-5 w-5 shrink-0"
                  checked={scopes.has(scope)}
                  onChange={() => toggleScope(scope)}
                />
                <span className="flex min-w-0 flex-col">
                  <span className="font-medium text-ink">{t(`scopes.${scope.replace(":", "_")}`)}</span>
                  <span className="break-all font-mono text-xs text-muted">{scope}</span>
                </span>
              </label>
            ))}
          </fieldset>
          <div>
            <Button type="submit" disabled={!canCreate}>
              {busy ? t("form.creating") : t("form.create")}
            </Button>
          </div>
        </form>
      </Card>

      <Card title={t("list.title")} titleId="key-list" actions={<span className="text-[13px] text-muted">{t("list.count", { n: keys.length })}</span>}>
        {keys.length === 0 ? (
          <p className="m-0 text-[15px]">{t("list.empty")}</p>
        ) : (
          <ul className="m-0 flex list-none flex-col p-0">
            {keys.map((key) => {
              const revoked = Boolean(key.revoked_at);
              return (
                <li
                  key={key.id}
                  data-testid="api-key-row"
                  className={cn("flex flex-wrap items-start justify-between gap-3 border-b border-subtle py-3 last:border-0", revoked && "opacity-70")}
                >
                  <div className="flex min-w-0 flex-col gap-1">
                    <span className="flex flex-wrap items-center gap-2">
                      <span className="break-words font-medium text-ink">{key.name}</span>
                      <Badge variant={revoked ? "flag" : "success"}>{revoked ? t("list.revoked") : t("list.active")}</Badge>
                    </span>
                    <span className="break-all font-mono text-xs text-muted">{t("list.prefix", { prefix: key.prefix })}</span>
                    <span className="flex flex-wrap gap-1.5">
                      {key.scopes.map((s) => (
                        <Badge key={s}>{s}</Badge>
                      ))}
                    </span>
                    <span className="text-[13px] text-muted">
                      {t("list.created", { date: formatDate(locale, key.created_at, "short") })} ·{" "}
                      {key.last_used_at
                        ? t("list.lastUsed", { date: formatDate(locale, key.last_used_at, "short") })
                        : t("list.neverUsed")}
                    </span>
                  </div>
                  {!revoked &&
                    (confirming === key.id ? (
                      <div className="flex flex-wrap gap-2">
                        <Button variant="attention" onClick={() => void revoke(key.id)}>
                          {t("list.confirmRevoke")}
                        </Button>
                        <Button variant="secondary" onClick={() => setConfirming(null)}>
                          {t("list.cancel")}
                        </Button>
                      </div>
                    ) : (
                      <Button
                        variant="attentionOutline"
                        aria-label={t("list.revokeLabel", { name: key.name })}
                        onClick={() => setConfirming(key.id)}
                      >
                        {t("list.revoke")}
                      </Button>
                    ))}
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </div>
  );
}
