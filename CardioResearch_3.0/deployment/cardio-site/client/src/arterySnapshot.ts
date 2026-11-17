import {sectionMetrics} from './arteryGeometry';
import type {Lang} from './ui';
import type {ArteryFrame} from './arteryComparison';

type SnapshotDetails={lang:Lang;narrowing:number;sectionPosition:number;cutaway:boolean};

/** Copy the fresh WebGL frame synchronously, before awaiting PNG encoding. */
export function arterySnapshot(frame:ArteryFrame,details:SnapshotDetails):HTMLCanvasElement {
  const source=frame.canvas;
  if(!source.width||!source.height)throw new Error('Scene has no rendered dimensions');
  const output=document.createElement('canvas');output.width=1600;output.height=1280;
  const context=output.getContext('2d');if(!context)throw new Error('Canvas export is unavailable');
  const t=(ru:string,kk:string)=>details.lang==='kk'?kk:ru;
  const section=sectionMetrics(details.sectionPosition,details.narrowing);
  context.fillStyle='#133742';context.fillRect(0,0,output.width,output.height);
  context.fillStyle='#f2fbf9';context.font='600 37px "Segoe UI",sans-serif';
  context.fillText(t('CardioResearch · 3D-артерия','CardioResearch · 3D-артерия'),56,67);
  context.fillStyle='#bed5db';context.font='23px "Segoe UI",sans-serif';
  context.fillText(t('Учебная схема атеросклероза — не изображение пациента','Атеросклероздың оқу сызбасы — пациенттің суреті емес'),56,111);
  context.fillStyle='#9fe4d5';context.font='24px "Segoe UI",sans-serif';
  context.fillText(t(`Макс. сужение диаметра: ${details.narrowing}%   ·   Срез x = ${section.position.toFixed(1)}   ·   Разрез ${details.cutaway?'включён':'выключен'}`,
    `Диаметрдің ең үлкен тарылуы: ${details.narrowing}%   ·   Қима x = ${section.position.toFixed(1)}   ·   Бойлық қима ${details.cutaway?'қосулы':'өшірулі'}`),56,155);
  const comparison=frame.views.length===2;
  const boxes=comparison?[{x:48,y:222,width:736,height:780},{x:816,y:222,width:736,height:780}]:[{x:48,y:182,width:1504,height:820}];
  frame.views.forEach((view,index)=>{
    const box=boxes[index],scale=Math.min(box.width/view.width,box.height/view.height);
    const width=view.width*scale,height=view.height*scale;
    context.drawImage(source,view.left,view.top,view.width,view.height,box.x+(box.width-width)/2,box.y+(box.height-height)/2,width,height);
    if(comparison){
      context.fillStyle='#e5f5f0';context.font='600 25px "Segoe UI",sans-serif';
      context.fillText(view.kind==='reference'?t('Без сужения · площадь среза 100%','Тарылусыз · қима ауданы 100%'):t(`Сужение ${details.narrowing}% · площадь среза ${section.areaPercent.toFixed(1)}%`,`Тарылу ${details.narrowing}% · қима ауданы ${section.areaPercent.toFixed(1)}%`),box.x+8,210);
    }
  });
  if(comparison){context.strokeStyle='#496772';context.lineWidth=1;context.beginPath();context.moveTo(800,190);context.lineTo(800,1000);context.stroke();}
  context.strokeStyle='#496772';context.lineWidth=1;context.beginPath();context.moveTo(56,1022);context.lineTo(1544,1022);context.stroke();
  const legends=[['#d58591',t('Стенка','Қабырға')],['#e6b45f',t('Бляшка','Түйіндақ')],['#73c6c1',t('Просвет','Қуыс')],['#ed6774',t('Частицы','Бөлшектер')],['#9de6ee',t('Выбранный срез','Таңдалған қима')]];
  context.font='22px "Segoe UI",sans-serif';
  legends.forEach(([color,label],i)=>{const x=58+i*290;context.fillStyle=color;context.beginPath();context.arc(x+7,1065,7,0,Math.PI*2);context.fill();context.fillStyle='#e5f0ee';context.fillText(label,x+25,1073)});
  context.fillStyle='#d9eeea';context.font='24px "Segoe UI",sans-serif';
  context.fillText(t(`Выбранный срез: диаметр ${section.diameterPercent.toFixed(1)}% · площадь просвета ${section.areaPercent.toFixed(1)}% исходной`,
    `Таңдалған қима: диаметр бастапқының ${section.diameterPercent.toFixed(1)}% · қуыс ауданы ${section.areaPercent.toFixed(1)}%`),56,1131);
  context.fillStyle='#aec7ce';context.font='21px "Segoe UI",sans-serif';
  context.fillText(t('Геометрия задаётся вручную. Координаты условные; кровоток и риск заболевания не рассчитываются.',
    'Геометрия қолмен беріледі. Координаталар шартты; қан ағыны мен ауру қаупі есептелмейді.'),56,1186);
  context.fillText(t('Снимок модели не содержит медицинских данных пациента и не связан с оценкой ML-модели.',
    'Модель суретінде пациенттің медициналық деректері жоқ және ол ML бағасымен байланысты емес.'),56,1225);
  return output;
}
