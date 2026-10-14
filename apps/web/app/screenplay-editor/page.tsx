import ScreenplayEditor from "../../components/ScreenplayEditor";
export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ interview?: string; screenplay?: string }>;
}) {
  const params = await searchParams;
  return (
    <ScreenplayEditor
      initialInterview={params.interview}
      initialScreenplay={params.screenplay}
    />
  );
}
