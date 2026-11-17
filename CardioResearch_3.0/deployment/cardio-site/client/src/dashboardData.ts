export type DashboardBin={lower:number;upper:number;n:number;mean_probability:number|null;observed_rate:number|null};
export type DashboardEvaluation={
 dataset:string;model:string;evaluation:string;threshold:number;n:number;positive:number;negative:number;
 metrics:Record<string,number|null>;confusion:[[number,number],[number,number]];
 calibration:DashboardBin[];
};
export const dashboardMetric=(value:unknown):number|null=>typeof value==='number'&&Number.isFinite(value)?value:null;
const share=(value:number,total:number)=>total>0?value/total:null;
export function dashboardSummary(record:DashboardEvaluation,expectedDataset:string){
 if(record.dataset!==expectedDataset)throw new Error('Dashboard dataset mismatch');
 const counts=[record.n,record.positive,record.negative,...record.confusion.flat()];
 if(counts.some(n=>!Number.isSafeInteger(n)||n<0)||record.n===0)throw new Error('Invalid dashboard counts');
 const [[tn,fp],[fn,tp]]=record.confusion;
 if(tn+fp!==record.negative||fn+tp!==record.positive||record.negative+record.positive!==record.n)throw new Error('Dashboard aggregate totals do not match');
 if(record.calibration.some(bin=>!Number.isSafeInteger(bin.n)||bin.n<0)||record.calibration.reduce((n,bin)=>n+bin.n,0)!==record.n)throw new Error('Calibration counts do not match the evaluation sample');
 const prevalence=record.positive/record.n;
 const ap=dashboardMetric(record.metrics.average_precision);
 return {tn,fp,fn,tp,prevalence,ap,apDifference:ap===null?null:ap-prevalence,
  detectedShare:share(tp,record.positive),missedShare:share(fn,record.positive),
  correctNegativeShare:share(tn,record.negative),falsePositiveShare:share(fp,record.negative)};
}
export function dashboardCalibration(bins:DashboardBin[]){
 return bins.flatMap((bin,index)=>{
  const x=dashboardMetric(bin.mean_probability),y=dashboardMetric(bin.observed_rate);
  return bin.n>0&&x!==null&&y!==null&&x>=0&&x<=1&&y>=0&&y<=1?[{index,x,y,n:bin.n,lower:bin.lower,upper:bin.upper}]:[];
 });
}
