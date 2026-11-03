"use client";

import { useTranslations } from "next-intl";
import { SkeletonGroup } from "@/components/ui/Skeleton";

/** Shown while a dataset screen loads its data on the server (every lifecycle step). */
export default function Loading() {
  const t = useTranslations("common");
  return (
    <main id="main" className="mx-auto flex max-w-container flex-col gap-6 px-6 pb-12 pt-8" aria-busy="true">
      <p className="m-0 text-[15px] text-muted" role="status">
        {t("loading")}
      </p>
      <SkeletonGroup lines={8} />
    </main>
  );
}
