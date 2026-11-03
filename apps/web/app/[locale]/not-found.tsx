import { useTranslations } from "next-intl";
import { ButtonLink } from "@/components/ui/Button";

export default function NotFound() {
  const t = useTranslations("common.notFoundPage");
  return (
    <main id="main" className="mx-auto flex max-w-container flex-col items-start gap-4 px-6 pb-12 pt-12">
      <h1 className="m-0 text-[30px] font-semibold text-ink">{t("title")}</h1>
      <p className="m-0 max-w-xl text-base text-muted">{t("body")}</p>
      <ButtonLink href="/">{t("home")}</ButtonLink>
    </main>
  );
}
