import {KeyboardEvent, PointerEvent} from 'react';
import {clampSectionPosition, HALF_ARTERY_LENGTH, lumenRadius, sectionMetrics} from './arteryGeometry';
import type {T} from './ui';

type Props = {narrowing:number; position:number; onChange:(position:number)=>void; t:T};
const LEFT=30, WIDTH=580, MIDDLE=88, SCALE=43;
const xToSvg=(x:number)=>LEFT+(x+HALF_ARTERY_LENGTH)/(2*HALF_ARTERY_LENGTH)*WIDTH;
const rounded=(x:number)=>clampSectionPosition(Math.round(x*10)/10);

/** A section selector using the same normalized geometry as the 3D model. */
export default function ArteryProfile({narrowing,position,onChange,t}:Props) {
  const points=Array.from({length:97},(_,i)=>-HALF_ARTERY_LENGTH+i/96*2*HALF_ARTERY_LENGTH);
  const edge=(sign:number)=>points.map(x=>`${xToSvg(x).toFixed(2)},${(MIDDLE+sign*lumenRadius(x,narrowing)*SCALE).toFixed(2)}`);
  const lumen=`M${edge(-1).join(' L')} L${edge(1).reverse().join(' L')} Z`;
  const marker=xToSvg(position), section=sectionMetrics(position,narrowing);
  const selectAt=(event:PointerEvent<SVGSVGElement>)=>{
    const rect=event.currentTarget.getBoundingClientRect();
    if(!rect.width)return;
    const svgX=(event.clientX-rect.left)/rect.width*640;
    onChange(rounded((svgX-LEFT)/WIDTH*2*HALF_ARTERY_LENGTH-HALF_ARTERY_LENGTH));
  };
  const onKey=(event:KeyboardEvent<SVGSVGElement>)=>{
    const next=event.key==='ArrowLeft'||event.key==='ArrowDown'?position-.1:
      event.key==='ArrowRight'||event.key==='ArrowUp'?position+.1:
      event.key==='PageDown'?position-1:event.key==='PageUp'?position+1:
      event.key==='Home'?-HALF_ARTERY_LENGTH:event.key==='End'?HALF_ARTERY_LENGTH:null;
    if(next===null)return;event.preventDefault();onChange(rounded(next));
  };
  return <div className="artery-profile">
    <div className="artery-profile-heading"><span>{t('Продольный профиль','Бойлық профиль')}</span><output>x = {position.toFixed(1)}<small>{t('условные единицы','шартты бірлік')}</small></output></div>
    <svg viewBox="0 0 640 172" preserveAspectRatio="none" role="slider" tabIndex={0}
      aria-label={t('Положение сечения на продольном профиле','Бойлық профильдегі қима орны')}
      aria-valuemin={-HALF_ARTERY_LENGTH} aria-valuemax={HALF_ARTERY_LENGTH} aria-valuenow={position}
      aria-valuetext={t(`x = ${position.toFixed(1)}; диаметр ${section.diameterPercent.toFixed(1)}% исходного.`,`x = ${position.toFixed(1)}; диаметр бастапқының ${section.diameterPercent.toFixed(1)}%.`)}
      onKeyDown={onKey} onPointerDown={event=>{event.currentTarget.focus();event.currentTarget.setPointerCapture(event.pointerId);selectAt(event)}}
      onPointerMove={event=>{if(event.currentTarget.hasPointerCapture(event.pointerId))selectAt(event)}}
      onPointerUp={event=>{if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId)}}>
      <rect x={LEFT} y={MIDDLE-SCALE*1.2} width={WIDTH} height={SCALE*2.4} rx="4" fill="#c87989"/>
      <rect x={LEFT} y={MIDDLE-SCALE} width={WIDTH} height={SCALE*2} fill="#e1b15f"/>
      <path d={lumen} fill="#163c48" stroke="#7bcbc7" strokeWidth="1.5"/>
      <path d={`M${LEFT} ${MIDDLE-SCALE}H${LEFT+WIDTH} M${LEFT} ${MIDDLE+SCALE}H${LEFT+WIDTH}`} stroke="#f4efe0" strokeOpacity=".4" strokeDasharray="4 6" fill="none"/>
      <path d={`M${LEFT} ${MIDDLE}H${LEFT+WIDTH}`} stroke="#9dbec4" strokeOpacity=".3" strokeDasharray="3 5"/>
      <path d={`M${marker} 20V143`} stroke="#a5eff5" strokeWidth="2"/>
      <path d={`M${marker-6} 15H${marker+6}L${marker} 23Z`} fill="#a5eff5"/>
      <circle cx={marker} cy={143} r="5" fill="#a5eff5"/>
      {[-3.6,-1.8,0,1.8,3.6].map(x=><text key={x} x={xToSvg(x)} y="165" textAnchor="middle" fill="#afc9ce" fontSize="11">{x===0?'0':x.toFixed(1)}</text>)}
    </svg>
    <p>{t('Нажмите или перетащите линию среза. Стрелки: шаг 0,1; Home / End: края.','Қима сызығын басыңыз немесе жылжытыңыз. Бағыттау пернелері: 0,1 қадам; Home / End: шеттер.')}</p>
  </div>;
}
