import { notFound } from "next/navigation";

/** Unknown paths under /en or /es get the translated not-found page, inside the layout. */
export default function CatchAll() {
  notFound();
}
