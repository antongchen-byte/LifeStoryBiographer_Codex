import ComingSoon from "../../components/ComingSoon";
export default function Page() {
  return (
    <ComingSoon
      title="Screenplay Editor"
      description="Turn remembered moments into a story with shape."
      steps={[
        "Select a story and its sources",
        "Craft scenes and narration",
        "Review and approve the screenplay",
      ]}
    />
  );
}
