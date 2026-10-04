import TranscriptReview from "../../../../../components/TranscriptReview";
export default async function Page({
  params,
}: {
  params: Promise<{ profileId: string; sourceId: string }>;
}) {
  const { profileId, sourceId } = await params;
  return <TranscriptReview profileId={profileId} sourceId={sourceId} />;
}
