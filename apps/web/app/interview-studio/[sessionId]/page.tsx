import InterviewStudio from "../../../components/InterviewStudio";
export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ sessionId: string }>;
  searchParams: Promise<{ begin?: string }>;
}) {
  const { sessionId } = await params;
  const { begin } = await searchParams;
  return (
    <InterviewStudio
      key={sessionId}
      view="conversation"
      sessionId={sessionId}
      begin={begin === "1"}
    />
  );
}
