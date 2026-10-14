import CinemaStudio from "../../components/CinemaStudio";
export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ screenplay?: string }>;
}) {
  const params = await searchParams;
  return <CinemaStudio screenplayId={params.screenplay} />;
}
