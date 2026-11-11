import InterviewStudio from "../../components/InterviewStudio";
export default async function Page({searchParams}:{searchParams:Promise<{config?:string}>}) {
 const {config}=await searchParams;
 return <InterviewStudio key={config || "configure"} view="configure" initialConfig={config} />;
}
