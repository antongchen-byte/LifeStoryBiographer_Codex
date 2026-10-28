import { notFound } from "next/navigation";
import ScreenplayEditor from "../../components/ScreenplayEditor";
export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ interview?: string; screenplay?: string }>;
}) {
  if (process.env.NEXT_PUBLIC_ENABLE_FILM_STUDIOS === "false") notFound();
  const params = await searchParams;
  return (
    <ScreenplayEditor
      initialInterview={params.interview}
      initialScreenplay={params.screenplay}
    />
  );
}
