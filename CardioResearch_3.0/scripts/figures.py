from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports'/'figures';OUT.mkdir(exist_ok=True)
B=json.loads((ROOT/'reports/brfss_results.json').read_text(encoding='utf-8'));U=json.loads((ROOT/'reports/uci_results.json').read_text(encoding='utf-8'))
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'axes.grid':True,'grid.alpha':.18,'savefig.dpi':170})
def save(name):plt.tight_layout();plt.savefig(OUT/(name+'.png'),bbox_inches='tight',facecolor='white');plt.close()
for key,title,xlabel,ylabel in [('roc','ROC қисықтары','Жалған оң жауап үлесі','Шынайы оң жауап үлесі'),('pr','Precision–Recall қисықтары','Сезімталдық','Оң болжам дәлдігі'),('calibration','Ықтималдықтарды калибрлеу','Орташа болжам','Нақты оң жауап үлесі')]:
    plt.figure(figsize=(7.3,4.1))
    for r in B['full']:plt.plot(r['curves'][key]['x'],r['curves'][key]['y'],label=r['name'],linewidth=2)
    if key in ['roc','calibration']:plt.plot([0,1],[0,1],'--',color='gray',linewidth=.8)
    plt.title(title+' · BRFSS толық тест');plt.xlabel(xlabel);plt.ylabel(ylabel);plt.legend();save(key)
plt.figure(figsize=(7.4,4.5));rs=B['benchmark'];plt.barh([r['name'] for r in rs],[r['metrics']['average_precision'] for r in rs],color='#258873');plt.xlabel('Average Precision');plt.title('Бірдей 12 000 бақылауда оқытылған модельдер');save('benchmark')
plt.figure(figsize=(7.4,4.5));rs=U['benchmark'];plt.barh([r['name'] for r in rs],[r['metrics']['average_precision'] for r in rs],xerr=[r['std']['average_precision'] for r in rs],color='#547da2',capsize=3);plt.xlabel('Average Precision · орташа және стандартты ауытқу');plt.title('UCI Cleveland · сыртқы CV 3 × 2');save('uci')
plt.figure(figsize=(7.4,4.1));tc=B['threshold_curve'];
for metric,label in [('precision','Оң болжам дәлдігі'),('recall','Сезімталдық'),('f1','F1')]:plt.plot([r['threshold'] for r in tc],[r[metric] for r in tc],label=label,linewidth=2)
plt.axvline(B['selection']['threshold'],linestyle='--',color='gray',label='Таңдалған шек');plt.xlabel('Классификация шегі');plt.ylabel('Метрика');plt.legend();plt.title('Шекті таңдау · тек валидациялық деректер');save('threshold')
labels={'age_group':'Жас тобы','general_health':'Жалпы денсаулық','sex':'Жыныс','hypertension':'Жоғары қысым','cholesterol':'Холестерин','diabetes':'Диабет','smoking':'Темекі шегу','physical_days':'Физикалық жайсыздық','bmi':'Дене салмағы индексі','activity':'Белсенділік','mental_days':'Эмоциялық жайсыздық'}
rs=list(reversed(B['importance']));plt.figure(figsize=(7.4,4.5));plt.barh([labels[r['feature']] for r in rs],[r['mean'] for r in rs],xerr=[r['std'] for r in rs],color='#258873');plt.xlabel('Average Precision төмендеуі');plt.title('Permutation importance · валидациялық таңдама');save('importance')
selected=next(r for r in B['full'] if r['name']==B['selection']['deployed_model']);cm=np.array(selected['metrics']['confusion']);plt.figure(figsize=(5.5,4.3));plt.imshow(cm,cmap='Greens');
for (i,j),v in np.ndenumerate(cm):plt.text(j,i,str(int(v)),ha='center',va='center',color='white' if v>40000 else '#20362a',fontsize=16)
plt.xticks([0,1],['Болжам 0','Болжам 1']);plt.yticks([0,1],['Нақты 0','Нақты 1']);plt.grid(False);plt.title('Қателер матрицасы · BRFSS');save('confusion')
print('Created',len(list(OUT.glob('*.png'))),'figures')
