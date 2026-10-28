import { notFound } from "next/navigation";
import CinemaStudio from "../../components/CinemaStudio";
export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ screenplay?: string }>;
}) {
  if (process.env.NEXT_PUBLIC_ENABLE_FILM_STUDIOS === "false") notFound();
  const params = await searchParams;
  return <CinemaStudio screenplayId={params.screenplay} />;
}
