from pathlib import Path
p=Path(__file__).resolve().parents[1]/'frontend/src/main.tsx'
t=p.read_text(encoding='utf-8')
t=t.replace("const go=(p:string)=>{setPage(p);setMenu(false);setError('')};","const go=(p:string)=>{setPage(p);setMenu(false);setError('');window.scrollTo({top:0,behavior:'instant'})};")
target="{research.full&&<Card title=\"Оценка с весами обследования\""
addition='''{research.threshold_curve&&<Card title="Выбор исследовательского порога" subtitle="Валидационная часть · порог максимума F1"><Chart data={['precision','recall','f1'].map(k=>({x:research.threshold_curve.map((r:any)=>r.threshold),y:research.threshold_curve.map((r:any)=>r[k]),type:'scatter',mode:'lines',name:names[k]}))} layout={{xaxis:{title:{text:'Порог'}},yaxis:{title:{text:'Метрика'}}}}/></Card>}<Card title="Вычислительные затраты" subtitle="Время измерено на одном компьютере; поиск включает CV и повторное обучение"><div className="table-scroll"><table><thead><tr><th>Модель</th><th>Обучающих наблюдений</th><th>Поиск / обучение, с</th><th>Предсказание теста, с</th></tr></thead><tbody>{tableRows.map((r:any)=><tr key={r.name}><td>{r.name}</td><td>{r.training_n}</td><td>{fmt(r.search_seconds??r.fit_seconds,2)}</td><td>{r.predict_seconds===undefined?'Включено во внешнюю CV':fmt(r.predict_seconds,3)}</td></tr>)}</tbody></table></div></Card>'''
if addition not in t:t=t.replace(target,addition+target)
p.write_text(t,encoding='utf-8')
