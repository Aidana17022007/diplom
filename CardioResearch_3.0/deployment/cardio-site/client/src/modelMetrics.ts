export const metricLabels: Record<string,string> = {roc_auc:'ROC-AUC',average_precision:'Average Precision',accuracy:'Accuracy',precision:'Precision',recall:'Recall',specificity:'Specificity',f1:'F1',brier:'Brier score',balanced_accuracy:'Balanced accuracy',mcc:'MCC',npv:'NPV',fpr:'FPR',fnr:'FNR'};
export type MetricDefinition={direction:'higher'|'lower';threshold:boolean;unit:'score'|'proportion';ru:string;kk:string};
export const metricDefinitions:Record<string,MetricDefinition>={
  roc_auc:{direction:'higher',threshold:false,unit:'score',ru:'Насколько оценки разделяют два класса по всем порогам. 0,5 — случайное ранжирование.',kk:'Бағалар барлық шектер бойынша екі сыныпты қаншалықты ажыратады. 0,5 — кездейсоқ ранжирлеу.'},
  average_precision:{direction:'higher',threshold:false,unit:'score',ru:'Качество ранжирования положительного класса по precision–recall. Зависит от доли положительного класса.',kk:'Precision–recall бойынша оң сыныпты ранжирлеу сапасы. Оң сыныптың үлесіне тәуелді.'},
  accuracy:{direction:'higher',threshold:true,unit:'proportion',ru:'Доля верных ответов среди всех наблюдений. При дисбалансе может скрывать пропуск редкого класса.',kk:'Барлық бақылаулар ішіндегі дұрыс жауаптар үлесі. Теңгерімсіздікте сирек сыныпты өткізіп алуды жасыруы мүмкін.'},
  precision:{direction:'higher',threshold:true,unit:'proportion',ru:'Доля фактически положительных среди положительных ответов модели. Зависит от порога и доли класса.',kk:'Модельдің оң жауаптары ішіндегі нақты оң бақылаулар үлесі. Шек пен сынып үлесіне тәуелді.'},
  recall:{direction:'higher',threshold:true,unit:'proportion',ru:'Доля обнаруженных среди фактически положительных наблюдений; чувствительность.',kk:'Нақты оң бақылаулар ішіндегі анықталғандардың үлесі; сезімталдық.'},
  specificity:{direction:'higher',threshold:true,unit:'proportion',ru:'Доля верно распознанных среди фактически отрицательных наблюдений; специфичность.',kk:'Нақты теріс бақылаулар ішіндегі дұрыс танылғандардың үлесі; ерекшелік.'},
  f1:{direction:'higher',threshold:true,unit:'score',ru:'Гармоническое среднее precision и recall. Не учитывает истинно отрицательные ответы.',kk:'Precision мен recall гармониялық орташа мәні. Дұрыс теріс жауаптарды ескермейді.'},
  brier:{direction:'lower',threshold:false,unit:'score',ru:'Средняя квадратичная ошибка вероятностей. Оценивает всю вероятность, а не только выбранный класс.',kk:'Ықтималдықтардың орташа квадраттық қатесі. Тек таңдалған сыныпты емес, ықтималдықтың өзін бағалайды.'},
  balanced_accuracy:{direction:'higher',threshold:true,unit:'proportion',ru:'Среднее recall и specificity: каждому фактическому классу дан одинаковый вес.',kk:'Recall мен specificity орташа мәні: әр нақты сыныпқа бірдей салмақ беріледі.'},
  mcc:{direction:'higher',threshold:true,unit:'score',ru:'Корреляция фактических и предсказанных классов. Учитывает все четыре вида ответов; диапазон −1…1.',kk:'Нақты және болжанған сыныптар корреляциясы. Жауаптың төрт түрін де ескереді; аралығы −1…1.'},
  npv:{direction:'higher',threshold:true,unit:'proportion',ru:'Доля фактически отрицательных среди отрицательных ответов модели. Зависит от доли класса и порога.',kk:'Модельдің теріс жауаптары ішіндегі нақты теріс бақылаулар үлесі. Сынып үлесі мен шекке тәуелді.'},
  fpr:{direction:'lower',threshold:true,unit:'proportion',ru:'Доля ложных срабатываний среди фактически отрицательных: FP / (TN + FP).',kk:'Нақты теріс бақылаулар ішіндегі жалған оң жауаптар үлесі: FP / (TN + FP).'},
  fnr:{direction:'lower',threshold:true,unit:'proportion',ru:'Доля пропущенных среди фактически положительных: FN / (TP + FN).',kk:'Нақты оң бақылаулар ішіндегі өткізіп алынғандар үлесі: FN / (TP + FN).'},
};
export function interpretMetricDelta(key:string,delta:number|null|undefined):{direction:'higher'|'lower'|null;numericPreference:'A'|'B'|'equal'|'unavailable'|'unknown';percentagePoints:number|null}{
  const definition=metricDefinitions[key];
  if(!finiteMetric(delta))return {direction:definition?.direction??null,numericPreference:'unavailable',percentagePoints:null};
  if(!definition)return {direction:null,numericPreference:'unknown',percentagePoints:null};
  return {direction:definition.direction,numericPreference:delta===0?'equal':(definition.direction==='higher'?delta>0:delta<0)?'B':'A',percentagePoints:definition.unit==='proportion'?delta*100:null};
}
export type ComparisonContext = {dataset:string;experiment:string;evaluation:string;weighting:string};
export type DerivedMethod={method:'confusion_counts'|'mean_of_fold_metrics'|'unavailable';folds:number|null;sd:'sample_ddof_1'|null;undefined_metrics:string[]};
export type ModelRow = {name:string; threshold?:number;test_n?:number|string;training_n?:number|string; metrics?:Record<string,unknown>; std?:Record<string,number|null|undefined>;folds?:{confusion?:unknown}[];derived_metrics?:DerivedMethod};
export const finiteMetric = (value:unknown):value is number => typeof value==='number' && Number.isFinite(value);
export const derivedMetricKeys=['balanced_accuracy','mcc','npv','fpr','fnr'] as const;
type DerivedScores=Record<typeof derivedMetricKeys[number],number|null>;
export function metricsFromConfusion(matrix:unknown):DerivedScores{
  const unavailable=():DerivedScores=>({balanced_accuracy:null,mcc:null,npv:null,fpr:null,fnr:null});
  if(!Array.isArray(matrix)||matrix.length!==2||!matrix.every(row=>Array.isArray(row)&&row.length===2))return unavailable();
  const values=matrix.flat();
  if(!values.every(value=>finiteMetric(value)&&value>=0))return unavailable();
  const [tn,fp,fn,tp]=values as number[],n=tn+fp+fn+tp;
  if(!Number.isFinite(n)||n<=0)return unavailable();
  const ratio=(a:number,b:number)=>b>0?a/b:null;
  const recall=ratio(tp,tp+fn),specificity=ratio(tn,tn+fp);
  // Normalizing cells avoids overflow in the fourth-order MCC denominator.
  const [a,b,c,d]=[tn,fp,fn,tp].map(value=>value/n);
  const denominator=Math.sqrt((d+b)*(d+c)*(a+b)*(a+c));
  return {balanced_accuracy:recall===null||specificity===null?null:(recall+specificity)/2,
    mcc:denominator>0?Math.max(-1,Math.min(1,(a*d-b*c)/denominator)):null,
    npv:ratio(tn,tn+fn),fpr:ratio(fp,tn+fp),fnr:ratio(fn,tp+fn)};
}
export function enrichMetricsRows(rows:ModelRow[],context?:ComparisonContext):ModelRow[]{
  return rows.map(row=>{
    // Outer-CV means must be formed from each fold, never from pooled or OOF counts.
    const isFoldEvaluation=context?.evaluation==='mean_outer_cv_6_folds'||Array.isArray(row.folds);
    const metrics={...row.metrics},std={...row.std};
    let method:DerivedMethod['method']='unavailable',foldCount:number|null=null;
    if(isFoldEvaluation){
      if(row.folds?.length){
        method='mean_of_fold_metrics';foldCount=row.folds.length;
        const folds=row.folds.map(fold=>metricsFromConfusion(fold?.confusion));
        for(const key of derivedMetricKeys){
          const values=folds.map(fold=>fold[key]);
          if(values.every(finiteMetric)){
            const mean=values.reduce((sum,value)=>sum+value,0)/values.length;
            metrics[key]=mean;std[key]=values.length>1?Math.sqrt(values.reduce((sum,value)=>sum+(value-mean)**2,0)/(values.length-1)):null;
          }else {metrics[key]=null;std[key]=null;}
        }
      }else for(const key of derivedMetricKeys){metrics[key]=null;std[key]=null;}
    }else{
      const derived=metricsFromConfusion(row.metrics?.confusion);
      method=Object.values(derived).some(finiteMetric)?'confusion_counts':'unavailable';
      for(const key of derivedMetricKeys){metrics[key]=derived[key];std[key]=null;}
    }
    return {...row,metrics,std,derived_metrics:{method,folds:foldCount,sd:method==='mean_of_fold_metrics'&&Number(foldCount)>1?'sample_ddof_1':null,undefined_metrics:derivedMetricKeys.filter(key=>!finiteMetric(metrics[key]))}};
  });
}
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
