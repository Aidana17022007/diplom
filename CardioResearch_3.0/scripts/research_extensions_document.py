"""Render measured research extensions from saved JSON, in Kazakh."""
from pathlib import Path
import json,sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
SOURCES=[
    '[10] Weng SF, Reps J, Kai J, Garibaldi JM, Qureshi N. Can machine-learning improve cardiovascular risk prediction using routine clinical data? PLOS ONE. 2017;12(4):e0174944. https://doi.org/10.1371/journal.pone.0174944',
    '[11] Saito T, Rehmsmeier M. The Precision-Recall Plot Is More Informative than the ROC Plot When Evaluating Binary Classifiers on Imbalanced Datasets. PLOS ONE. 2015;10(3):e0118432. https://doi.org/10.1371/journal.pone.0118432',
    '[12] Van Calster B, McLernon DJ, van Smeden M, Wynants L, Steyerberg EW. Calibration: the Achilles heel of predictive analytics. BMC Medicine. 2019;17:230. https://doi.org/10.1186/s12916-019-1466-7',
    '[13] SHAP documentation. ExactExplainer; PermutationExplainer. https://shap.readthedocs.io/en/latest/generated/shap.ExactExplainer.html ; https://shap.readthedocs.io/en/latest/generated/shap.PermutationExplainer.html. Тексерілген: 17.11.2026. Жобада сыртқы SHAP пакеті шақырылмайды.'
]


def read(name):return json.loads((ROOT/'reports'/name).read_text(encoding='utf-8'))


def draw_figures():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch
    r=read('literature_experiments.json'); e=read('explanation_audit.json')
    out=ROOT/'reports/figures';out.mkdir(exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,ax=plt.subplots(figsize=(7.4,3.7))
    rows=r['prevalence_scenarios'];x=[v['assumed_prevalence']*100 for v in rows]
    for key,label,color in [('roc_auc','ROC-AUC','#506a82'),('average_precision','Average Precision','#168579'),('precision_fixed_threshold','Precision, бекітілген шек','#b57c4c')]:
        ax.plot(x,[v[key] for v in rows],marker='o',label=label,color=color)
    ax.set(xlabel='Оң класс үлесі, % (шартты сценарий)',ylabel='Көрсеткіш',ylim=(0,1));ax.grid(alpha=.2);ax.legend(fontsize=9)
    fig.tight_layout();fig.savefig(out/'research_prevalence.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(7.4,3.7))
    for ax,d in zip(axes,e['datasets']):
        ax.plot([x['permutations'] for x in d['summary']],[x['mean_mae_pp'] for x in d['summary']],marker='o',color='#168579')
        ax.set(title=d['dataset'].upper(),xlabel='Пермутация саны',ylabel='Орташа абсолют қате, п.т.');ax.set_xticks([12,48,192]);ax.grid(alpha=.2)
    fig.tight_layout();fig.savefig(out/'research_shap_precision.png',dpi=170);plt.close(fig)
    # Architecture follows the saved benchmark configuration; no invented weights.
    b=read('brfss_results.json');mlp=next(x for x in b['benchmark'] if x['name']=='MLP')
    import joblib
    bundle=joblib.load(ROOT/'models/brfss.joblib')
    n_inputs=len(bundle.pipeline.named_steps['pre'].get_feature_names_out())
    hidden=mlp['best_params']['model__hidden_layer_sizes']
    (ROOT/'reports/research_mlp_architecture.json').write_text(json.dumps({'original_features':len(bundle.features),'encoded_inputs':n_inputs,'hidden_layers':hidden,'output_units':1,'source':'Saved BRFSS benchmark best_params and shared fixed-schema preprocessing','learned_weights_visualized':False},indent=2)+'\n',encoding='utf-8')
    fig,ax=plt.subplots(figsize=(7.4,3.1));ax.set(xlim=(0,10),ylim=(0,4));ax.axis('off')
    texts=[f'{len(bundle.features)} бастапқы белгі\nBRFSS сауалнамасы',f'Pipeline\n{n_inputs} сандық кіріс',f'MLP\nжасырын қабат: '+', '.join(map(str,hidden)),'1 шығыс\nтіркелген жағдай']
    for i,text in enumerate(texts):
        xx=.1+i*2.5
        ax.add_patch(FancyBboxPatch((xx,1.25),2.1,1.4,boxstyle='round,pad=0.1',facecolor='#eaf3f0',edgecolor='#338477'))
        ax.text(xx+1.05,1.95,text,ha='center',va='center',fontsize=10)
        if i<3:ax.annotate('',xy=(xx+2.45,1.95),xytext=(xx+2.2,1.95),arrowprops={'arrowstyle':'->','color':'#506a82'})
    ax.text(5,.65,'Қабаттар сызбасы; сызықтар үйретілген салмақтарды көрсетпейді.',ha='center',fontsize=9)
    fig.tight_layout();fig.savefig(out/'research_mlp_architecture.png',dpi=170);plt.close(fig)


def add_sections(doc, standalone=False):
    r=read('literature_experiments.json');e=read('explanation_audit.json')
    def section(number,title):
        if standalone and number>1:doc.page()
        doc.h(f'{number if standalone else "4."+str(number+9)} {title}',1 if standalone else 2)
    section(1,'Бос мән туралы ақпаратты жеке белгі ретінде тексеру')
    doc.p('Weng және әріптестерінің зерттеуінде кейбір өлшемдердің жоқтығын жеке индикатормен көрсету қарастырылған [10]. Осы идея BRFSS-те бөлек абляция ретінде тексерілді. Ұлыбританиядағы клиникалық жазбаның толтырылмауы мен сауалнамадағы жауаптың болмауы бірдей үдеріс емес; осы себепті мақала қорытындысы біздің деректерге автоматты көшірілмейді.')
    doc.p('Бастапқы оқыту жиынындағы бекітілген 12 000 жол және бірдей үш стратификацияланған бөлу қолданылды. Екі нұсқада да Logistic Regression, C=1 және класс салмағынсыз оқыту сақталды. Өзгерген жалғыз қадам — сандық медианалық толтыруға missing indicator қосу. Индикаторлар мен барлық үйренілетін өңдеу тек тиісті оқыту бөлігінде анықталды. Тест жиыны қолданылмады; жаңа ең үздік модель таңдалмады.')
    doc.table(['Нұсқа','AP орташа','ROC-AUC','Brier','Өңделген белгі'],[
        ['Индикаторсыз' if not v['numeric_missing_indicators'] else 'Сандық бос мән индикаторымен',f"{v['mean']['average_precision']:.6f}",f"{v['mean']['roc_auc']:.6f}",f"{v['mean']['brier']:.6f}",v['folds'][0]['transformed_features']] for v in r['missingness']
    ],[165,85,85,85,75])
    delta=r['missingness'][1]['mean']['average_precision']-r['missingness'][0]['mean']['average_precision']
    doc.p(f'AP айырмасы {delta:+.8f}. Бұл шағын тәжірибе индикаторлардан елеулі ұтыс бар деген тұжырымды қолдамайды; Brier сәл нашарлады. Үш CV бағасы тәуелсіз клиникалық таңдама емес және статистикалық маңыздылық тексерілген жоқ. Қолданыстағы модель өзгертілмеді. Толық fold нәтижелері reports/literature_experiments.json ішінде сақталған.')
    section(2,'Класс жиілігі және Precision мен Average Precision')
    doc.p('Saito мен Rehmsmeier сирек оң класс жағдайында ROC қисығын Precision–Recall талдауымен толықтыру қажеттігін көрсетеді [11]. Осы қағиданы өз деректерімізде түсіндіру үшін BRFSS-тің бекітілген 85 748 тест болжамына класс бойынша тұрақты салмақ берілді. Әр сынып ішіндегі бағалар таралуы өзгермеді; тек сыныптардың салыстырмалы үлесі ауыстырылды. Бұл жаңа пациенттер де, BRFSS сауалнама салмақтары да емес.')
    doc.table(['Шартты оң үлес','ROC-AUC','Average Precision','Precision'],[[f"{v['assumed_prevalence']:.3%}",f"{v['roc_auc']:.4f}",f"{v['average_precision']:.4f}",f"{v['precision_fixed_threshold']:.4f}"] for v in r['prevalence_scenarios']],[125,120,130,120])
    doc.figure('research_prevalence','Сынып үлесі өзгеретін шартты сценарийлер. Бірдей бағалар және бекітілген зерттеу шегі; бұл модельдерді қайта оқыту нәтижесі емес.')
    doc.p(f"Шек {r['threshold']:.6f} деңгейінде сақталды. ROC-AUC шамамен 0,8389 болып қалса да, Precision мен AP өзгерді. Precision = TPR × π / (TPR × π + FPR × (1 − π)), мұнда π — оң класс үлесі. Нақты ортада сынып ішіндегі таралулар да өзгеруі мүмкін; бұл қарапайым сценарий Қазақстандағы нәтижені болжамайды. AP scikit-learn average_precision_score арқылы есептелді, трапециялық PR-AUC-пен араластырылмайды.")
    section(3,'Ықтималдықтардың калибрленуін сандық бағалау')
    doc.p('Van Calster және әріптестерінің мақаласына сүйеніп, орташа болжам мен нақты жиіліктің айырмасына қоса калибрлеу intercept және slope есептелді [12]. Бірінші диагностикалық модель logit(y ықтималдығы) = a + logit(p), яғни slope=1 бекітіледі. Екінші модель a + b×logit(p) түрінде екі коэффициентті бағалайды. Қажетті бағдарлар: offset intercept=0 және slope=1. Бұл коэффициенттер тестте тек сипаттама үшін есептелді және қолданыстағы болжамды түзетуге қолданылған жоқ.')
    doc.table(['Нұсқа','Орташа қате, п.т.','Offset intercept','Slope','Brier'],[[v['version'],f"{v['mean_error_pp']:+.5f}",f"{v['intercept_slope_fixed_1']:+.5f}",f"{v['slope']:.5f}",f"{v['brier']:.8f}"] for v in r['calibration']],[135,95,95,75,95])
    doc.p('Екі диагностикалық intercept бір шама емес: кестеде slope=1 кезінде бағаланған offset intercept көрсетілген; slope босатылған модельдің intercept мәні JSON есебінде бөлек берілді. Қосымша sigmoid Brier-ді аздап төмендеткенімен, орташа болжамның жиіліктен ауытқуы артты. Сондықтан «калибрлеу барлық көрсеткішті жақсартты» деуге болмайды. Нөлге жақын intercept пен бірге жақын slope әр ішкі топта мінсіз калибрлеуді дәлелдемейді. Сенімділік интервалдары осы қосымша диагностикада есептелмеді.')
    section(4,'Жеке түсіндірмелердің сандық дәлдігі мен тұрақтылығы')
    doc.p('Қосындының дұрыс болуы әр белгінің жеке үлесі дәл бағаланғанын білдірмейді. Осы айырмашылықты тексеру үшін қолданыстағы 48 пермутациялық есептеу толық коалициялық есептеумен салыстырылды [13]. BRFSS үшін 11 белгі бойынша 2 048 коалиция, UCI үшін 13 белгі бойынша 8 192 коалиция қаралды. «Дәл» деген сөз бекітілген 30 фондық жол үшін есептеуді білдіреді; ол популяциялық немесе себептік ақиқат емес.')
    doc.p('Әр дерек жиынына сақталған оқыту фондының алғашқы 30 жолынан тыс алты профиль seed=20261117 арқылы таңдалды. Бір фонға қатысты 12, 48 және 192 пермутация 20 seed-пен салыстырылды. Барлығы 720 профиль–seed–бюджет комбинациясы есептелді, бірақ олар 720 тәуелсіз пациент емес. Профильдің жеке кіріс мәндері есепте жарияланбайды. API-дегі нақты есептеу мен коалиция кэшінен алынған есептеу сәйкестігі барлық 12 профильде тексерілді.')
    doc.table(['Дерек','Пермутация','Орташа MAE, п.т.','Ең үлкен қате, п.т.','Top-3 сәйкес үлес'],[
        [d['dataset'].upper(),v['permutations'],f"{v['mean_mae_pp']:.5f}",f"{v['worst_error_pp']:.5f}",f"{v['mean_top3_overlap']:.1%}"] for d in e['datasets'] for v in d['summary']
    ],[70,80,115,115,115])
    doc.figure('research_shap_precision','Толық коалициялық есепке қатысты пермутациялық үлестердің қатесі. Әр қисық — алты профиль мен 20 seed бойынша орташа; сенімділік интервалы көрсетілмеген.')
    doc.table(['Дерек','48 реттегі MAE, п.т.','Фон ауысқандағы MAE, п.т.'],[[d['dataset'].upper(),f"{next(v['mean_mae_pp'] for v in d['summary'] if v['permutations']==48):.5f}",f"{np.mean([p['background_change']['mae_pp'] for p in d['profiles_detail']]):.5f}"] for d in e['datasets']],[115,180,200])
    doc.p('Фонға сезімталдық басқа, қиылыспайтын 30 оқыту жолымен толық есептеу арқылы өлшенді. Фон ауысқандағы айырмашылық пермутациялық қатеден үлкен болды. Бұл екі шама әртүрлі: пермутациялық қате бірдей түсіндірме нысанын жуықтайды, ал басқа фон бастапқы салыстыру тобын және түсіндірменің өзін өзгертеді. Бір балама фон мен алты профиль жалпы халыққа қорытынды жасауға жеткіліксіз. Негізгі модель, 48 пермутациялық қолданба алгоритмі және шешім шегі осы тәжірибеден кейін өзгертілген жоқ.')
    section(5,'Нейрондық желі сызбасын дұрыс қолдану')
    doc.p('Пайдаланушы ұсынған сурет Weng мақаласының 2-суретіне сәйкес келеді [10]. Ондағы CPRD белгілері мен желі салмақтарын BRFSS моделінің нәтижесі ретінде көрсетуге болмайды. Төмендегі сызба өз жобамыздың сақталған benchmark конфигурациясы мен ортақ өңдеу құрылымынан алынды; үйретілген MLP салмақтары қайта жасалмаған.')
    architecture=read('research_mlp_architecture.json')
    doc.figure('research_mlp_architecture',f"BRFSS салыстырмалы тәжірибесіндегі MLP конфигурациясы. {architecture['original_features']} бастапқы белгі өңделгеннен кейін {architecture['encoded_inputs']} кіріске өтеді; жасырын қабат: {architecture['hidden_layers']}. Байланыстардың салмақтары көрсетілмейді.")
    doc.p('Бұл — зерттелген кандидаттың архитектурасы, қолданбадағы негізгі BRFSS моделі емес. Қолданба логистикалық регрессияны пайдаланады. Weng мақаласындағы он жылдық болашақ оқиға міндеті мен CardioResearch-тегі тіркелген жағдайды жіктеу бөлек. Қосымшадағы түсіндірме белгінің модель бағасына ықпалын сипаттайды, аурудың себебін анықтамайды.')


def standalone_report():
    from build_documents import Document
    doc=Document('CardioResearch ғылыми талдауын толықтыру')
    doc.p('CardioResearch ғылыми талдауын толықтыру',style='TitleKK')
    doc.p('Сарсенбаева Айдананың дипломдық жобасына арналған өлшенген қосымша тәжірибелер. 17 қараша 2026 жыл. Қазақша жұмыс материалы; негізгі қолжазбаны автор тексеріп, өз тұжырымдарымен біріктіруі қажет.')
    doc.p('Үш мақала негізінде бос мән индикаторларының әсері, класс жиілігінің метрикаларға ықпалы және ықтималдықтардың калибрленуі зерттелді. Оған қосымша модель түсіндірмесінің сандық дәлдігі мен фондық деректерге сезімталдығы өлшенді. Негізгі модельдерді ауыстыру немесе клиникалық тиімділік туралы тұжырым жасалмайды.')
    doc.page();add_sections(doc,standalone=True)
    doc.page();doc.h('Дереккөздер және қайта орындау')
    for source in SOURCES:doc.p(source,style='SmallKK')
    doc.p('Хаттамалар есептеуге дейін сақталды: reports/explanation_audit_protocol.json және reports/literature_experiments_protocol.json. Бұл бастапқы диплом хаттамасынан кейінгі қосымша зерттеу; оны бастапқы алдын ала тіркеу ретінде көрсетуге болмайды.')
    doc.table(['Команда','Нәтиже'],[['python -m scripts.audit_explanations --pilot','Уақыт пен бастапқы сандық сәйкестік'],['python -m scripts.audit_explanations','Түсіндірмелердің дәлдігі және фон сезімталдығы'],['python -m scripts.literature_experiments','Бос мән, жиілік және калибрлеу тәжірибелері'],['python scripts/research_extensions_document.py','Суреттер және осы есеп']],[270,225])
    doc.p('Модельдер мен бастапқы метрика файлдарының SHA-256 сомалары әр тәжірибенің алдында және соңында салыстырылды. Олардың өзгермегені JSON есептерінде расталған. Бақылаулардың тәуелділігі, шектеулі фон және BRFSS күрделі сауалнама жоспары қорытындыларды шектейді. Сайт дизайны мен интернеттегі жариялау осы зерттеу жаңартуында өзгертілмеді.')
    doc.save('CardioResearch_research_extension_KZ')


if __name__=='__main__':
    draw_figures();standalone_report()
