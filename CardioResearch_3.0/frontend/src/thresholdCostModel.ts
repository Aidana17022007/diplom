import {thresholdPoint,ThresholdPoint} from './thresholdComparison';

export type CostAssumptions={falseNegativeWeight:number;minRecall:number;maxPositiveFraction:number};
export type CostRow={point:ThresholdPoint;weightedErrors:number;lossPer1000:number;positiveFraction:number;feasible:boolean};
export type CostResult={status:'ok'|'invalid_assumptions'|'unavailable';assumptions:CostAssumptions;rows:CostRow[];baseline:CostRow|null;selected:CostRow|null;ties:number[];feasibleCount:number};
export const DEFAULT_COST_ASSUMPTIONS:CostAssumptions={falseNegativeWeight:5,minRecall:0,maxPositiveFraction:1};

/** A hypothetical loss on saved validation counts; never a clinical threshold rule. */
export function evaluateThresholdCosts(points:ThresholdPoint[],reference:ThresholdPoint|null,assumptions:CostAssumptions):CostResult{
 const result:CostResult={status:'unavailable',assumptions:{...assumptions},rows:[],baseline:null,selected:null,ties:[],feasibleCount:0};
 if(!Number.isInteger(assumptions.falseNegativeWeight)||assumptions.falseNegativeWeight<1||assumptions.falseNegativeWeight>20||
   !Number.isFinite(assumptions.minRecall)||assumptions.minRecall<0||assumptions.minRecall>1||
   !Number.isFinite(assumptions.maxPositiveFraction)||assumptions.maxPositiveFraction<0||assumptions.maxPositiveFraction>1){
  result.status='invalid_assumptions';return result;
 }
 if(!reference||reference.source!=='working'||!Array.isArray(points)||!points.length)return result;
 const baseline=thresholdPoint(reference.threshold,reference.confusion,'working');
 if(!baseline)return result;
 const saved=new Map<number,ThresholdPoint>();
 for(const input of points){
  const point=thresholdPoint(input?.threshold,input?.confusion,'grid');
  if(!point||point.positive!==baseline.positive||point.negative!==baseline.negative)return result;
  const previous=saved.get(point.threshold);
  if(previous&&JSON.stringify(previous.confusion)!==JSON.stringify(point.confusion))return result;
  saved.set(point.threshold,point);
 }
 const savedReference=saved.get(baseline.threshold);
 if(savedReference&&JSON.stringify(savedReference.confusion)!==JSON.stringify(baseline.confusion))return result;
 saved.set(baseline.threshold,baseline);
 const score=(point:ThresholdPoint):CostRow=>{
  const weightedErrors=point.counts.fp+assumptions.falseNegativeWeight*point.counts.fn;
  const positiveFraction=(point.counts.tp+point.counts.fp)/point.n;
  // Zero disables the recall constraint; undefined recall cannot meet a positive minimum.
  const recallAllowed=assumptions.minRecall===0||(point.metrics.recall!==null&&point.metrics.recall>=assumptions.minRecall);
  return {point,weightedErrors,lossPer1000:weightedErrors/point.n*1000,positiveFraction,
   feasible:recallAllowed&&positiveFraction<=assumptions.maxPositiveFraction};
 };
 const rows=[...saved.values()].sort((a,b)=>a.threshold-b.threshold).map(score);
 if(rows.some(row=>!Number.isSafeInteger(row.weightedErrors)))return result;
 const feasible=rows.filter(row=>row.feasible);
 const minimum=feasible.length?Math.min(...feasible.map(row=>row.weightedErrors)):null;
 const tied=feasible.filter(row=>row.weightedErrors===minimum);
 // Preserve the working reference on a tie; otherwise use the smallest measured threshold.
 const selected=tied.find(row=>row.point.source==='working')??tied[0]??null;
 return {...result,status:'ok',rows,baseline:rows.find(row=>row.point.source==='working')!,selected,
  ties:tied.map(row=>row.point.threshold),feasibleCount:feasible.length};
}

export function thresholdCostsCsv(result:CostResult,model:string):string{
 if(result.status!=='ok'||!result.baseline)return '';
 const a=result.assumptions;
 const header=['dataset','model','evaluation','weighting','decision_rule','scope','fp_penalty','fn_penalty','min_recall','recall_constraint_enabled','max_positive_fraction','working_threshold','selected_threshold','feasible_points','minimum_tie_count','tie_break','threshold','working_reference','feasible','selected_for_display','minimum_tie','n','positive','negative','tn','fp','fn','tp','recall','precision','positive_fraction','weighted_errors','penalty_per_1000','penalty_delta_from_working_per_1000'];
 const rows=result.rows.map(row=>['brfss',model,'validation','unweighted','probability >= threshold','exploratory_hypothetical_penalty',1,a.falseNegativeWeight,a.minRecall,a.minRecall>0,a.maxPositiveFraction,result.baseline!.point.threshold,result.selected?.point.threshold??null,result.feasibleCount,result.ties.length,'working_reference_then_lowest_measured_threshold',row.point.threshold,row.point.source==='working',row.feasible,row===result.selected,result.ties.includes(row.point.threshold),row.point.n,row.point.positive,row.point.negative,row.point.counts.tn,row.point.counts.fp,row.point.counts.fn,row.point.counts.tp,row.point.metrics.recall,row.point.metrics.precision,row.positiveFraction,row.weightedErrors,row.lossPer1000,row.lossPer1000-result.baseline!.lossPer1000]);
 const cell=(value:unknown)=>{
  if(value===null||value===undefined)return '';
  const s=typeof value==='string'&&/^[=+\-@\t\r]/.test(value)?"'"+value:String(value);
  return /[",\r\n]/.test(s)?'"'+s.replace(/"/g,'""')+'"':s;
 };
 return [header,...rows].map(row=>row.map(cell).join(',')).join('\r\n')+'\r\n';
}
