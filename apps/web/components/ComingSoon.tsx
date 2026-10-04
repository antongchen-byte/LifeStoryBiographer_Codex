import Link from "next/link";
import { ArrowLeft, Sparkles } from "lucide-react";
export default function ComingSoon({
  title,
  description,
  steps,
}: {
  title: string;
  description: string;
  steps: string[];
}) {
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">YOUR BIOGRAPHY STUDIO</span>
          <h1>{title}</h1>
          <p className="muted">{description}</p>
        </div>
        <span className="status-pill">Coming next</span>
      </div>
      <div className="coming-soon">
        <Sparkles size={38} strokeWidth={1} />
        <h2>Great stories begin with good material.</h2>
        <p>
          This part of the studio is still being built. Start by collecting your
          photos, recordings, and documents in a biography’s Media Library.
        </p>
        <div className="future-steps">
          {steps.map((step, i) => (
            <div key={step}>
              <span>0{i + 1}</span>
              {step}
            </div>
          ))}
        </div>
        <Link className="button button-primary" href="/">
          <ArrowLeft size={16} />
          Back to my biographies
        </Link>
      </div>
    </>
  );
}
