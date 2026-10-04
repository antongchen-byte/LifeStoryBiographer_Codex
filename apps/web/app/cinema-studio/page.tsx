import ComingSoon from "../../components/ComingSoon";
export default function Page() {
  return (
    <ComingSoon
      title="Cinema Studio"
      description="Bring a life story to the screen."
      steps={[
        "Plan the look of your film",
        "Create and curate each shot",
        "Assemble a film to keep",
      ]}
    />
  );
}
