import {useEffect, useRef, useState, RefObject} from 'react';
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {clampSectionPosition, lumenRadius, sectionMetrics} from './arteryGeometry';
import {arteryViewports, ArteryFrame} from './arteryComparison';
import type {T} from './ui';

export type ArteryCapture={capture:()=>ArteryFrame|null};
type Props = {compare?:boolean;narrowing: number; sectionPosition: number; cutaway: boolean; moving: boolean; reset: number; view: 'side' | 'end' | 'top'; highlight:'wall'|'plaque'|'lumen'; t: T; captureRef:RefObject<ArteryCapture|null>; onReady:(ready:boolean)=>void; onUnavailable?:()=>void};
type SceneApi = {compare:(enabled:boolean)=>void;update: (n: number, cut: boolean) => void; section: (position: number) => void; motion:(moving:boolean)=>void; highlight:(part:Props['highlight'])=>void; reset: (view: Props['view']) => void};

function surface(point: (u: number, v: number) => number[], nu = 64, nv = 72) {
  const positions: number[] = [], indices: number[] = [];
  for (let i = 0; i <= nu; i++) for (let j = 0; j <= nv; j++) positions.push(...point(i / nu, j / nv));
  for (let i = 0; i < nu; i++) for (let j = 0; j < nv; j++) {
    const a = i * (nv + 1) + j, b = a + nv + 1;
    indices.push(a, b, a + 1, b, b + 1, a + 1);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

export default function ArteryScene({compare=false, narrowing, sectionPosition, cutaway, moving, reset, view, highlight, t, captureRef, onReady, onUnavailable}: Props) {
  const host = useRef<HTMLDivElement>(null);
  const api = useRef<SceneApi | null>(null);
  const currentView = useRef(view);
  currentView.current = view;
  const [failed, setFailed] = useState(false);
  const [ready, setReady] = useState(false);
  const [stacked,setStacked]=useState(false);

  useEffect(() => {
    const container = host.current!;
    let renderer: THREE.WebGLRenderer;
    try { renderer = new THREE.WebGLRenderer({antialias: true, alpha: true}); }
    catch { setFailed(true); return; }

    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setClearColor(0x102e38, 0);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.domElement.setAttribute('aria-hidden', 'true');
    container.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(37, 1, 0.1, 100);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.enablePan = false;
    controls.minDistance = 5;
    controls.maxDistance = 19;
    // Scroll the page normally; use the explicit zoom controls for the scene.
    controls.enableZoom = false;
    scene.add(new THREE.HemisphereLight(0xe8f8ff, 0x5d293e, 2.6));
    const key = new THREE.DirectionalLight(0xfff4df, 3.2); key.position.set(0, 5, 6); scene.add(key);
    const rim = new THREE.DirectionalLight(0x77d4cf, 2); rim.position.set(-3, -2, -4); scene.add(rim);
    // Both models share one context, camera, controls, lights and materials.
    // Scissored views draw only when the existing render scheduler is active.
    const sectionRingGeometry = new THREE.TorusGeometry(1.32, .018, 8, 96);
    const sectionPlaneGeometry = new THREE.CircleGeometry(1.29, 72);
    const sectionRingMaterial = new THREE.MeshBasicMaterial({color:0x9de6ee, transparent:true, opacity:.95, depthTest:false, depthWrite:false});
    const sectionPlaneMaterial = new THREE.MeshBasicMaterial({color:0x7fd6e3, transparent:true, opacity:.10, side:THREE.DoubleSide, depthWrite:false});
    const wall = new THREE.MeshStandardMaterial({color: 0xb44c64, roughness: .59, side: THREE.DoubleSide});
    const lining = new THREE.MeshStandardMaterial({color: 0xe68b93, roughness: .5, side: THREE.DoubleSide});
    const cutWall = new THREE.MeshStandardMaterial({color: 0xf4b3aa, roughness: .75, side: THREE.DoubleSide});
    const plaque = new THREE.MeshStandardMaterial({color: 0xe6b45f, roughness: .68, side: THREE.DoubleSide});
    const plaqueCut = new THREE.MeshStandardMaterial({color: 0xffd58c, roughness: .8, side: THREE.DoubleSide});
    const lumenGuideMaterial = new THREE.LineBasicMaterial({color:0x91efe8, transparent:true, opacity:.9, depthWrite:false});
    const cellMaterial = new THREE.MeshStandardMaterial({color: 0xf05f69, roughness: .38});
    const cellGeometry = new THREE.TorusGeometry(.095, .046, 8, 16);
    function makeModel(n:number){
      const group=new THREE.Group(),vessel=new THREE.Group(),guide=new THREE.Group(),marker=new THREE.Group();
      group.add(vessel,guide,marker);scene.add(group);
      const ring=new THREE.Mesh(sectionRingGeometry,sectionRingMaterial),plane=new THREE.Mesh(sectionPlaneGeometry,sectionPlaneMaterial);
      ring.rotation.y=plane.rotation.y=Math.PI/2;ring.renderOrder=3;plane.renderOrder=2;
      marker.add(ring,plane);marker.position.x=clampSectionPosition(sectionPosition);
      const cells=Array.from({length:24},(_,i)=>{
        const cell=new THREE.Mesh(cellGeometry,cellMaterial);cell.rotation.set(i*.71,i*1.37,i*.41);group.add(cell);return cell;
      });
      return {group,vessel,guide,marker,cells,n};
    }
    const altered=makeModel(narrowing),reference=makeModel(0),models=[reference,altered];
    let comparing=compare,currentCut=cutaway,zoom=1,width=1,height=1;
    let phase = 0, motion = moving, inView = true, lost = false, disposed = false;
    let frame: number | null = null, previous = performance.now(), dirty = true;
    // Paused scenes render only on input/resize. Damping schedules frames until
    // OrbitControls settles; hidden scenes do not keep a requestAnimationFrame loop.
    const schedule = () => {
      if(frame===null && !disposed && !lost && inView && !document.hidden) frame=requestAnimationFrame(animate);
    };
    const draw = () => {dirty=true;schedule();};
    const stopFrame = () => {if(frame!==null)cancelAnimationFrame(frame);frame=null;};
    function animate(now:number) {
      frame=null;
      if(disposed || lost || !inView || document.hidden)return;
      const delta=Math.min((now-previous)/1000,.05);previous=now;
      const changed=controls.update();
      if(motion){phase=(phase+delta*.55)%7.2;positionCells();dirty=true;}
      if(dirty || changed){renderFrame();dirty=false;}
      if(motion || changed)schedule();
    }
    controls.addEventListener('change',draw);
    function renderFrame(){
      if(!width||!height)return;
      renderer.setScissorTest(false);renderer.setViewport(0,0,width,height);renderer.clear();
      renderer.setScissorTest(true);
      for(const pane of arteryViewports(width,height,comparing)){
        reference.group.visible=pane.kind==='reference';altered.group.visible=pane.kind==='altered';
        camera.aspect=pane.width/pane.height;
        // Keep the whole longitudinal model visible in narrow comparison panes.
        camera.zoom=zoom*Math.min(1,camera.aspect/1.4);camera.updateProjectionMatrix();
        const bottom=height-pane.top-pane.height;
        renderer.setViewport(pane.left,bottom,pane.width,pane.height);
        renderer.setScissor(pane.left,bottom,pane.width,pane.height);
        renderer.render(scene,camera);
      }
      renderer.setScissorTest(false);
    }
    renderer.autoClear=false;
    function rebuildModel(model:ReturnType<typeof makeModel>,n:number,cut:boolean){
      model.n=n;
      model.vessel.children.forEach(obj=>(obj as THREE.Mesh).geometry.dispose());model.vessel.clear();
      model.guide.children.forEach(obj=>(obj as THREE.Line).geometry.dispose());model.guide.clear();
      const start=cut?1.95:0,end=cut?6.05:Math.PI*2;
      const xyz=(x:number,r:number,a:number)=>[x,r*Math.cos(a),r*Math.sin(a)];
      const add=(g:THREE.BufferGeometry,m:THREE.Material)=>model.vessel.add(new THREE.Mesh(g,m));
      add(surface((u,v)=>xyz((u-.5)*7.2,1.2,start+v*(end-start))),wall);
      add(surface((u,v)=>xyz((u-.5)*7.2,1,start+v*(end-start))),lining);
      for(const x of [-3.6,3.6])add(surface((u,v)=>xyz(x,1+u*.2,start+v*(end-start)),2),cutWall);
      if(cut)for(const a of [start,end])add(surface((u,v)=>xyz((u-.5)*7.2,1+v*.2,a),24,2),cutWall);
      if(n>0){
        add(surface((u,v)=>{const x=(u-.5)*5.2;return xyz(x,lumenRadius(x,n)-.002,start+v*(end-start));}),plaque);
        if(cut)for(const a of [start,end])add(surface((u,v)=>{const x=(u-.5)*5.2,r=lumenRadius(x,n);return xyz(x,r+v*(1-r),a);},64,2),plaqueCut);
      }
      for(const a of [start,end,(start+end)/2]){
        const points=Array.from({length:81},(_,i)=>{
          const x=-3.6+i/80*7.2;return new THREE.Vector3(...xyz(x,lumenRadius(x,n)-.012,a) as [number,number,number]);
        });
        model.guide.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(points),lumenGuideMaterial));
      }
    }
    function rebuild(n:number,cut:boolean){
      rebuildModel(altered,n,cut);
      if(cut!==currentCut||!reference.vessel.children.length)rebuildModel(reference,0,cut);
      currentCut=cut;positionCells();draw();
    }
    function positionCells(){
      for(const model of models)model.cells.forEach((cell,i)=>{
        const x=((i/model.cells.length*7.2+phase)%7.2)-3.6,angle=i*2.399;
        const radius=Math.max(0,lumenRadius(x,model.n)-.19)*(.25+(i%5)*.13);
        cell.position.set(x,radius*Math.cos(angle),radius*Math.sin(angle));
      });
    }
    function resetView(next: Props['view']) {
      // Flush any residual orbit inertia before applying a deterministic preset.
      controls.enableDamping=false;controls.update();
      camera.position.set(...(next === 'end' ? [11.8, .01, .01] : next==='top' ? [.01,11.8,.01] : [3.5, 3.7, 10.2]) as [number, number, number]);
      zoom=1; camera.zoom = 1; camera.updateProjectionMatrix(); controls.target.set(0, 0, 0); controls.update();controls.enableDamping=true;draw();
    }
    function emphasize(part:Props['highlight']) {
      for(const material of [wall,lining,cutWall]){
        material.emissive.setHex(part==='wall'?0x79303c:0x000000);material.emissiveIntensity=part==='wall'?.28:0;
      }
      for(const material of [plaque,plaqueCut]){
        material.emissive.setHex(part==='plaque'?0xa56c18:0x000000);material.emissiveIntensity=part==='plaque'?.3:0;
      }
      models.forEach(model=>{model.guide.visible=part==='lumen'});draw();
    }
    api.current = {compare:enabled=>{comparing=enabled;draw();},update: rebuild, section: position => {models.forEach(model=>{model.marker.position.x=clampSectionPosition(position)});draw();},
      motion:value=>{motion=value;previous=performance.now();draw();},highlight:emphasize,reset: resetView};
    captureRef.current={capture:()=>{
      if(disposed||lost||!width||!height||!renderer.domElement.width||!renderer.domElement.height)return null;
      // No preserveDrawingBuffer: the consumer copies this fresh frame in the
      // same task, before yielding to PNG encoding or browser composition.
      renderFrame();
      const ratioX=renderer.domElement.width/width,ratioY=renderer.domElement.height/height;
      return {canvas:renderer.domElement,views:arteryViewports(width,height,comparing).map(pane=>({...pane,left:pane.left*ratioX,top:pane.top*ratioY,width:pane.width*ratioX,height:pane.height*ratioY}))};
    }};
    resetView(view);
    rebuild(narrowing, cutaway);
    emphasize(highlight);
    const resize = new ResizeObserver(() => {
      width=container.clientWidth;height=container.clientHeight;
      if(!width||!height)return;
      setStacked(width<560);renderer.setSize(width,height);draw();
    });
    resize.observe(container);
    const intersection = new IntersectionObserver(([entry]) => {
      inView=entry.isIntersecting;
      if(inView){previous=performance.now();draw();}else stopFrame();
    }); intersection.observe(container);
    const onVisibility=()=>{if(document.hidden)stopFrame();else{previous=performance.now();draw();}};
    document.addEventListener('visibilitychange',onVisibility);
    const onLost = (event: Event) => {event.preventDefault();lost=true;stopFrame();setFailed(true);setReady(false);};
    renderer.domElement.addEventListener('webglcontextlost', onLost);
    const onKey = (event: KeyboardEvent) => {
      if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', '+', '=', '-', 'Home'].includes(event.key)) return;
      event.preventDefault();
      if (event.key === 'Home') resetView(currentView.current);
      else if (['+', '=', '-'].includes(event.key)) {
        zoom=THREE.MathUtils.clamp(zoom+(event.key==='-'?-.1:.1),.6,1.8);
      } else {
        const spherical = new THREE.Spherical().setFromVector3(camera.position);
        spherical.theta += event.key === 'ArrowLeft' ? -.14 : event.key === 'ArrowRight' ? .14 : 0;
        spherical.phi = THREE.MathUtils.clamp(spherical.phi + (event.key === 'ArrowUp' ? -.14 : event.key === 'ArrowDown' ? .14 : 0), .15, Math.PI - .15);
        camera.position.setFromSpherical(spherical); controls.update();
      }
      draw();
    };
    const onZoom = (event: Event) => {
      zoom=THREE.MathUtils.clamp(zoom+(event as CustomEvent<number>).detail,.6,1.8);draw();
    };
    container.addEventListener('keydown', onKey);
    container.addEventListener('artery-zoom', onZoom);
    setReady(true);
    return () => {
      disposed=true;stopFrame();resize.disconnect();intersection.disconnect();controls.removeEventListener('change',draw);controls.dispose();
      document.removeEventListener('visibilitychange',onVisibility);
      container.removeEventListener('keydown', onKey); container.removeEventListener('artery-zoom', onZoom);
      renderer.domElement.removeEventListener('webglcontextlost', onLost);
      models.forEach(model=>{model.vessel.children.forEach(obj=>(obj as THREE.Mesh).geometry.dispose());model.guide.children.forEach(obj=>(obj as THREE.Line).geometry.dispose());});lumenGuideMaterial.dispose();
      [wall, lining, cutWall, plaque, plaqueCut, cellMaterial].forEach(m => m.dispose()); cellGeometry.dispose();
      sectionRingGeometry.dispose(); sectionPlaneGeometry.dispose(); sectionRingMaterial.dispose(); sectionPlaneMaterial.dispose();
      renderer.dispose();renderer.forceContextLoss();renderer.domElement.remove();api.current=null;captureRef.current=null;
    };
    // Scene ownership is tied to mount. State updates below do not recreate WebGL contexts.
  }, []);
  useEffect(()=>{api.current?.compare(compare);},[compare]);
  useEffect(() => {api.current?.update(narrowing, cutaway);}, [narrowing, cutaway]);
  useEffect(() => {api.current?.section(sectionPosition);}, [sectionPosition]);
  useEffect(() => {api.current?.motion(moving);}, [moving]);
  useEffect(() => {api.current?.highlight(highlight);}, [highlight]);
  useEffect(() => {api.current?.reset(view);}, [reset, view]);
  useEffect(() => {onReady(ready&&!failed);}, [ready,failed,onReady]);
  useEffect(() => {if(failed)onUnavailable?.();}, [failed,onUnavailable]);

  const section=sectionMetrics(sectionPosition,narrowing);
  return <div className={'artery-renderer'+(compare?' artery-renderer-compare':'')+(stacked?' artery-renderer-stacked':'')}>
    <div ref={host} className="artery-canvas" role="group" tabIndex={0}
      aria-label={compare?t('Две 3D-модели артерии с общими ракурсом, масштабом и сечением. Стрелки — вращение, плюс и минус — масштаб, Home — сброс.','Ортақ ракурсы, масштабы және қимасы бар екі 3D артерия моделі. Бағыттау пернелері — айналдыру, плюс пен минус — масштаб, Home — қалпына келтіру.'):t('Интерактивная 3D-модель артерии. Стрелки — вращение, плюс и минус — масштаб, Home — сброс.','Артерияның интерактивті 3D моделі. Бағыттау пернелері — айналдыру, плюс пен минус — масштаб, Home — қалпына келтіру.')}
      aria-describedby="artery-description" style={failed ? {display: 'none'} : undefined}/>
    {compare&&!failed&&<div className="artery-compare-labels"><div><strong>{t('Без сужения','Тарылусыз')}</strong><span>{t('Исходная геометрия · площадь 100%','Бастапқы геометрия · аудан 100%')}</span></div><div><strong>{t('Заданное сужение','Берілген тарылу')} · {narrowing}%</strong><span>{t(`Площадь среза ${section.areaPercent.toFixed(1)}%`,`Қима ауданы ${section.areaPercent.toFixed(1)}%`)}</span></div></div>}
    {!ready && !failed && <div className="artery-loading" role="status">{t('Создаём 3D-модель…','3D модель жасалуда…')}</div>}
    {failed && <div className="artery-fallback" role="status"><strong>{t('3D недоступно в этом браузере','Бұл браузерде 3D қолжетімсіз')}</strong><p>{t('Продольный профиль, выбор среза и поперечные сечения продолжают работать без WebGL.','Бойлық профиль, қиманы таңдау және көлденең қималар WebGL болмаса да жұмыс істейді.')}</p></div>}
    {!failed && <div className="artery-zoom"><button type="button" onClick={() => host.current?.dispatchEvent(new CustomEvent('artery-zoom', {detail: .15}))} aria-label={t('Увеличить модель','Модельді үлкейту')}>+</button><button type="button" onClick={() => host.current?.dispatchEvent(new CustomEvent('artery-zoom', {detail: -.15}))} aria-label={t('Уменьшить модель','Модельді кішірейту')}>−</button></div>}
  </div>;
}
