export const metricLabels: Record<string,string> = {roc_auc:'ROC-AUC',average_precision:'Average Precision',accuracy:'Accuracy',precision:'Precision',recall:'Recall',specificity:'Specificity',f1:'F1',brier:'Brier score'};
export type ComparisonContext = {dataset:string;experiment:string;evaluation:string;weighting:string};
export type ModelRow = {name:string; threshold?:number;test_n?:number;training_n?:number; metrics?:Record<string,number|null|undefined>; std?:Record<string,number|null|undefined>};
export const finiteMetric = (value:unknown):value is number => typeof value==='number' && Number.isFinite(value);
export function sortedModels(rows:ModelRow[], metric:string, direction:'asc'|'desc') {
  if(!metric)return [...rows];
  return [...rows].sort((a,b)=>{
    const x=a.metrics?.[metric], y=b.metrics?.[metric];
    if(!finiteMetric(x))return finiteMetric(y)?1:0;
    if(!finiteMetric(y))return -1;
    return direction==='asc'?x-y:y-x;
  });
}
export function compareModels(a:ModelRow,b:ModelRow,keys:string[]) {
  return keys.map(key=>{
    const first=a.metrics?.[key], second=b.metrics?.[key];
    return {key,first:finiteMetric(first)?first:null,second:finiteMetric(second)?second:null,
      delta:finiteMetric(first)&&finiteMetric(second)?second-first:null};
  });
}
