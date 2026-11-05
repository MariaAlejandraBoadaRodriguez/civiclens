"use client";

import { useId, useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "@/i18n/routing";
import { ApiErrorNotice } from "@/components/ui/ApiErrorNotice";
import { Badge } from "@/components/ui/Badge";
import { Button, ButtonLink } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { StatusBanner } from "@/components/ui/StatusBanner";
import type { DomainResponse, RoleMapping } from "@/lib/api-types";
import { apiRequest, waitForJob, type ApiFailure } from "@/lib/apiClient";
import { cn } from "@/lib/cn";
import { formatPercent } from "@/lib/format";

type Save =
  | { state: "idle" }
  | { state: "saving"; percent: number; label: string }
  | { state: "saved"; pack: string }
  | { state: "error"; error: ApiFailure };

/**
 * Domain step after ingest: CivicLens suggests a domain pack, an analysis goal and which column
 * plays each of the pack's roles (with a confidence). The user confirms or edits the choice.
 * Unmapped roles only drop the pack items that need them; the generic analysis always stays.
 */
export function DomainStep({ domain, datasetRef, sample }: { domain: DomainResponse; datasetRef: string; sample: boolean }) {
  const t = useTranslations("domain");
  const locale = useLocale();
  const router = useRouter();
  const ids = useId();
  const scores = useMemo(() => Object.fromEntries(domain.suggestions.map((s) => [s.pack, s.score])), [domain.suggestions]);
  const [pack, setPack] = useState(domain.pack);
  const [goal, setGoal] = useState(domain.goal);
  const [roles, setRoles] = useState<Record<string, RoleMapping>>(domain.roles);
  const [save, setSave] = useState<Save>({ state: "idle" });

  const current = domain.packs.find((p) => p.id === pack) ?? domain.packs[0];
  const suggested = domain.suggestions[0];
  const columns = domain.columns;
  const byName = Object.fromEntries(columns.map((c) => [c.name, c]));
  const procurement = current.id === "government";

  function choosePack(id: string) {
    const next = domain.packs.find((p) => p.id === id);
    if (!next) return;
    setPack(id);
    setGoal((next.goals.find((g) => g.default) ?? next.goals[0]).id);
    // Back to the stored mapping for the stored pack; another pack starts from its suggestion.
    setRoles(id === domain.pack ? domain.roles : {});
    setSave({ state: "idle" });
  }

  function setColumn(roleId: string, column: string) {
    setRoles((prev) => {
      const next = { ...prev };
      if (!column) delete next[roleId];
      else next[roleId] = { column, confidence: 1, positive: prev[roleId]?.column === column ? prev[roleId]?.positive : null };
      return next;
    });
  }

  async function submit() {
    setSave({ state: "saving", percent: 5, label: t("saving") });
    const keepSuggestion = pack !== domain.pack && Object.keys(roles).length === 0;
    const res = await apiRequest<DomainResponse>(`/api/v1/datasets/${encodeURIComponent(datasetRef)}/domain`, {
      locale,
      method: "PUT",
      json: {
        pack,
        goal,
        roles: keepSuggestion
          ? null
          : Object.fromEntries(
              Object.entries(roles).map(([id, r]) => [id, { column: r.column, positive: r.positive ?? null }]),
            ),
      },
    });
    if (!res.ok) {
      setSave({ state: "error", error: res.error });
      return;
    }
    if (res.data.job) {
      const done = await waitForJob(res.data.job.id, locale, {
        onProgress: (job) => setSave({ state: "saving", percent: job.progress ?? 20, label: job.phase_label ?? t("saving") }),
      });
      if (!done.ok) {
        setSave({ state: "error", error: done.error });
        return;
      }
    }
    setRoles(res.data.roles);
    setSave({ state: "saved", pack: domain.packs.find((p) => p.id === res.data.pack)?.name ?? res.data.pack });
    router.refresh();
  }

  const showMapping = current.roles.length > 0 && !procurement;
  return (
    <Card
      title={t("title")}
      titleId="domain"
      actions={
        <Badge variant={domain.confirmed ? "success" : "info"}>
          {domain.confirmed ? t("confirmed") : t("suggested", { name: suggested?.name ?? current.name })}
        </Badge>
      }
    >
      <p className="m-0 text-[15px] text-text">{t("intro")}</p>

      <fieldset className="m-0 flex min-w-0 flex-col gap-2 border-0 p-0" disabled={sample}>
        <legend className="mb-2 p-0 text-sm font-medium text-ink">{t("packLegend")}</legend>
        <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
          {domain.packs.map((p) => {
            const score = scores[p.id] ?? 0;
            const blocked = p.id === "government" && score === 0;
            const active = p.id === pack;
            return (
              <label
                key={p.id}
                className={cn(
                  "flex min-h-touch cursor-pointer items-start gap-3 rounded-control border p-3 text-sm",
                  active ? "border-primary bg-primary-soft" : "border-line hover:bg-ground",
                  blocked && "cursor-not-allowed opacity-70",
                )}
              >
                <input
                  type="radio"
                  name={`${ids}-pack`}
                  value={p.id}
                  checked={active}
                  disabled={blocked}
                  onChange={() => choosePack(p.id)}
                  className="mt-1 h-4 w-4 accent-primary"
                />
                <span className="flex min-w-0 flex-col gap-1">
                  <span className="flex flex-wrap items-center gap-2 font-medium text-ink">
                    {p.name}
                    <span className="font-mono text-xs text-muted">{t("fit", { score: formatPercent(locale, score, 0) })}</span>
                  </span>
                  <span className="text-[13px] text-muted">{blocked ? t("notApplicable") : p.description}</span>
                </span>
              </label>
            );
          })}
        </div>
      </fieldset>

      <div className="flex flex-col gap-1.5">
        <label htmlFor={`${ids}-goal`} className="text-sm font-medium text-ink">
          {t("goal")}
        </label>
        <select
          id={`${ids}-goal`}
          value={goal}
          disabled={sample}
          onChange={(e) => setGoal(e.target.value)}
          className="min-h-touch max-w-[360px] rounded-nav border border-line-strong bg-surface px-2 text-sm"
        >
          {current.goals.map((g) => (
            <option key={g.id} value={g.id}>
              {g.name}
            </option>
          ))}
        </select>
      </div>

      {showMapping && (
        <div className="flex flex-col gap-2">
          <h3 className="m-0 text-sm font-medium text-ink">{t("roles.title")}</h3>
          <p className="m-0 text-[13px] text-muted">{t("roles.hint")}</p>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] border-collapse text-sm" data-testid="role-mapping">
              <caption className="sr-only">{t("roles.caption")}</caption>
              <thead>
                <tr className="border-b border-line text-left text-[13px] text-muted">
                  <th scope="col" className="py-2 pr-3 font-medium">{t("roles.role")}</th>
                  <th scope="col" className="py-2 pr-3 font-medium">{t("roles.column")}</th>
                  <th scope="col" className="py-2 pr-3 font-medium">{t("roles.confidence")}</th>
                  <th scope="col" className="py-2 font-medium">{t("roles.positive")}</th>
                </tr>
              </thead>
              <tbody>
                {current.roles.map((role) => {
                  const mapped = roles[role.id];
                  const options = columns.filter(
                    (c) =>
                      role.kinds.includes(c.kind) || (c.binary && role.kinds.includes("binary")) || c.name === mapped?.column,
                  );
                  const selectId = `${ids}-${role.id}`;
                  const top = mapped ? byName[mapped.column]?.top ?? [] : [];
                  return (
                    <tr key={role.id} className="border-b border-line align-top">
                      <th scope="row" className="py-2.5 pr-3 text-left font-normal">
                        <label htmlFor={selectId} className="flex flex-wrap items-center gap-1.5 text-ink">
                          {role.name}
                          {role.target && <Badge variant="info">{t("roles.target")}</Badge>}
                          {role.sensitive && <Badge variant="flag">{t("roles.sensitive")}</Badge>}
                        </label>
                      </th>
                      <td className="py-2.5 pr-3">
                        <select
                          id={selectId}
                          value={mapped?.column ?? ""}
                          disabled={sample}
                          onChange={(e) => setColumn(role.id, e.target.value)}
                          className="min-h-touch w-full max-w-[260px] rounded-nav border border-line-strong bg-surface px-2 font-mono text-sm"
                        >
                          <option value="">{t("roles.none")}</option>
                          {options.map((c) => (
                            <option key={c.name} value={c.name}>
                              {c.source} · {c.kind_label}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="py-2.5 pr-3 font-mono">
                        {!mapped ? (
                          <span className="text-muted">—</span>
                        ) : mapped.confidence === 1 ? (
                          t("roles.byYou")
                        ) : (
                          <span className={(mapped.confidence ?? 0) < 0.7 ? "text-flag" : undefined}>
                            {formatPercent(locale, mapped.confidence ?? 0, 0)}
                          </span>
                        )}
                      </td>
                      <td className="py-2.5">
                        {role.target && mapped && top.length > 0 ? (
                          <>
                            <label htmlFor={`${selectId}-positive`} className="sr-only">
                              {t("roles.positiveLabel", { role: role.name })}
                            </label>
                            <select
                              id={`${selectId}-positive`}
                              value={mapped.positive ?? ""}
                              disabled={sample}
                              onChange={(e) =>
                                setRoles((prev) => ({ ...prev, [role.id]: { ...mapped, positive: e.target.value || null } }))
                              }
                              className="min-h-touch rounded-nav border border-line-strong bg-surface px-2 font-mono text-sm"
                            >
                              <option value="">{t("roles.auto")}</option>
                              {top.map((v) => (
                                <option key={v} value={v}>
                                  {v}
                                </option>
                              ))}
                            </select>
                          </>
                        ) : (
                          <span className="text-muted">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {current.roles.some((r) => r.sensitive) && <p className="m-0 text-[13px] text-muted">{t("roles.sensitiveNote")}</p>}
        </div>
      )}
      {procurement && <p className="m-0 text-[13px] text-muted">{t("procurementNote")}</p>}

      {sample ? (
        <p className="m-0 text-[13px] text-muted">{t("sampleNote")}</p>
      ) : (
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={() => void submit()} disabled={save.state === "saving"}>
            {domain.confirmed || pack !== domain.pack ? t("save") : t("confirm")}
          </Button>
          <span className="text-[13px] text-muted">{t("saveHint")}</span>
        </div>
      )}
      {save.state === "saving" && <ProgressBar value={save.percent} label={save.label} />}
      {save.state === "saved" && (
        <StatusBanner
          variant="success"
          title={t("savedTitle", { name: save.pack })}
          actions={<ButtonLink href={`/datasets/${datasetRef}/sql`}>{t("openSql")}</ButtonLink>}
        >
          {t("savedBody")}
        </StatusBanner>
      )}
      {save.state === "error" && <ApiErrorNotice error={save.error} onRetry={() => void submit()} />}
    </Card>
  );
}
