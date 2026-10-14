import InterviewStudio from "../../../../components/InterviewStudio";
export default async function Page({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = await params;
  return (
    <InterviewStudio key={sessionId} view="review" sessionId={sessionId} />
  );
}
