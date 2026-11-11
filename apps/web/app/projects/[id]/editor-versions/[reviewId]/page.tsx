import ProductionReview from '../../../../../components/ProductionReview';
export default async function Page({params}:{params:Promise<{id:string;reviewId:string}>}){
 const {id,reviewId}=await params;
 return <ProductionReview projectId={id} reviewId={reviewId}/>;
}
