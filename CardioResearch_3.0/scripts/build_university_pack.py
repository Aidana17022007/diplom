"""Author auxiliary planning and verified reading catalog, not thesis body text."""
from pathlib import Path
import json, html, re
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/pdf'; OUT.mkdir(parents=True,exist_ok=True)
def read(name): return json.loads((ROOT/'reports'/name).read_text(encoding='utf-8'))
PROFILE=read('student_profile.json'); RULES=read('university_requirements.json')
for name,file in [('TimesKK','times.ttf'),('TimesKKB','timesbd.ttf'),('TimesKKI','timesi.ttf')]:
    pdfmetrics.registerFont(TTFont(name,'C:/Windows/Fonts/'+file))
pdfmetrics.registerFontFamily('TimesKK',normal='TimesKK',bold='TimesKKB',italic='TimesKKI',boldItalic='TimesKKB')
STYLE={
 'body':ParagraphStyle('body',fontName='TimesKK',fontSize=14,leading=16.2,alignment=TA_JUSTIFY,firstLineIndent=12.5*mm,spaceAfter=8),
 'h1':ParagraphStyle('h1',fontName='TimesKKB',fontSize=16,leading=19,spaceBefore=12,spaceAfter=16,keepWithNext=True),
 'h2':ParagraphStyle('h2',fontName='TimesKKB',fontSize=14,leading=17,spaceBefore=12,spaceAfter=10,keepWithNext=True),
 'small':ParagraphStyle('small',fontName='TimesKK',fontSize=11,leading=13.5,spaceAfter=8),
 'cell':ParagraphStyle('cell',fontName='TimesKK',fontSize=11,leading=13),
 'link':ParagraphStyle('link',fontName='TimesKK',fontSize=10,leading=12,spaceAfter=8,wordWrap='CJK'),
 'title':ParagraphStyle('title',fontName='TimesKKB',fontSize=20,leading=25,spaceAfter=20)
}
W=A4[0]-40*mm
def esc(x): return html.escape(str(x))
class Doc:
    def __init__(self,title): self.title=title;self.story=[];self.html=[]
    def p(self,t,style='body'):
        self.story.append(Paragraph(esc(t).replace('\n','<br/>'),STYLE[style])); self.html.append('<p>'+esc(t).replace('\n','<br>')+'</p>')
    def h(self,t,level=1):
        self.p(t,'h1' if level==1 else 'h2')
    def page(self): self.story.append(PageBreak());self.html.append('<div class="page"></div>')
    def link(self,url):
        if not url:return
        self.story.append(Paragraph(f'<a href="{esc(url)}" color="#124c82">{esc(url)}</a>',STYLE['link']))
        self.html.append(f'<p><a href="{esc(url)}">{esc(url)}</a></p>')
    def table(self,headers,rows,widths):
        dat=[[Paragraph(esc(x).replace('\n','<br/>'),STYLE['cell']) for x in row] for row in [headers]+rows]
        tab=Table(dat,colWidths=widths,repeatRows=1,hAlign='LEFT')
        tab.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8edf0')),('GRID',(0,0),(-1,-1),.4,colors.HexColor('#D9D9D9')),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
        self.story.extend([tab,Spacer(1,10)])
        self.html.append('<table>'+''.join('<tr>'+''.join('<td>'+esc(x)+'</td>' for x in row)+'</tr>' for row in [headers]+rows)+'</table>')
    def save(self,stem):
        def footer(c,d):
            c.setFont('TimesKK',10);c.drawCentredString(A4[0]/2,13*mm,str(d.page))
        doc=SimpleDocTemplate(str(OUT/(stem+'.pdf')),pagesize=A4,leftMargin=30*mm,rightMargin=10*mm,topMargin=20*mm,bottomMargin=25*mm,title=self.title,author='Codex assisted auxiliary preparation')
        doc.build(self.story,onFirstPage=footer,onLaterPages=footer)
        css='body{font-family:"Times New Roman",serif;font-size:14pt;line-height:1.16;max-width:170mm;margin:30px auto;color:black}p{text-align:justify}h1,h2{color:black}table{border-collapse:collapse;width:100%;font-size:11pt}td{border:1px solid #d9d9d9;padding:7px;overflow-wrap:anywhere}a{overflow-wrap:anywhere}tr:first-child{background:#e8edf0}.page{break-before:page}@media print{@page{size:A4;margin:20mm 10mm 25mm 30mm}body{margin:0}.page{page-break-before:always}}'
        (OUT/(stem+'.html')).write_text('<!doctype html><html lang="kk"><meta charset="utf-8"><title>'+esc(self.title)+'</title><style>'+css+'</style><body>'+''.join(self.html)+'</body></html>',encoding='utf-8')

def guide():
    d=Doc('100 беттік дипломды дайындау жоспары')
    d.p('100 беттік дипломды дайындау жоспары','title')
    d.p('Сарсенбаева Айдана · 2027 жыл','h2')
    d.p(PROFILE['approved_title_as_supplied'])
    d.p('Мәртебесі: ЕҰУ ережесіне сәйкестендіруге арналған көмекші жоспар. Құжатта көлем, рәсімдеу, әдебиеттермен жұмыс және орындалған зерттеуді тексеру тәртібі берілген. 100 беттік соңғы диплом әлі құрастырылған жоқ.')
    d.p('Негіз: ПОЛ ЕНУ 2.014-КV, 31.08.2026 өзгерістерімен берілген 55 беттік ереже. Сканерленген құжат мәтіні танылып, негізгі талаптар бет бейнелерімен салыстырылды. Төмендегі бет сілтемелері осы ережеге қатысты.')
    d.h('Көлемді есептеу')
    d.p('9.1-тармақта 40–50 бет көрсетілген; 9.14-тармақта дипломдық жұмыстың кіріспе, негізгі бөлім және қорытынды көлемі кемінде 50 бет, жобанікі кемінде 40 бет болуы тиіс делінген. Бұл жоспар мазмұндық бөлімге дәл 50 бет бөледі. Осылайша екі нұсқаның да төменгі талабы орындалады; кафедраның арнайы нұсқаулығы қосымша тексеріледі.')
    d.table(['Құрамдас бөлік','Бет саны'],[['Кіріспе + 3 тарау + қорытынды','50'],['Мұқаба, титул және бастапқы құжаттар','10'],['Әдебиеттер тізімі','5'],['Зерттеуге қатысты қосымшалар','35'],['Жалпы жоспар','100']],[W*.75,W*.25])
    d.p('100 бетке жету үшін қаріпті ұлғайту, бос бет қосу немесе бір ойды қайталау қолданылмайды. Қосымшалар негізгі мәтінде аталып, нақты деректерге, есептерге немесе бағдарламаның құжаттамасына сүйенуі тиіс.','small')
    d.page();d.h('1 Титул парағына берілген мәліметтер')
    d.table(['Өріс','Берілген мән'],[['Білім алушы',PROFILE['student']],['Тақырып',PROFILE['approved_title_as_supplied']],['Бағдарлама',PROFILE['programme']],['Белгі / код',PROFILE['programme_code_as_supplied']],['Топ',PROFILE['group']],['Жетекші',PROFILE['supervisor']],['Дәреже, берілген жазылуы',PROFILE['supervisor_degree_as_supplied']],['Қорғау жылы',str(PROFILE['defense_year'])],['Университет',PROFILE['university_from_regulation']]],[W*.31,W*.69])
    d.p('Факультет пен кафедраның толық ресми атауы әлі берілген жоқ. IDSAI белгісінің титулдағы орны және «Phdi» жазылуы ресми үлгімен нақтыланады. Қолтаңба, рұқсат беру күні, бұйрық нөмірі немесе бекітілген тапсырма ойдан толтырылмайды.')
    d.p('Мұқаба мен титул университет ережесінің 2 және 3-қосымшалары бойынша рәсімделеді. Ресми атау өзгеріссіз сақталады. Нақты зерттеу міндеті мәтінде MI/CHD туралы өзіндік есепті жіктеу деп түсіндіріледі; тақырыптағы «болжау» сөзі болашақтағы 5 немесе 10 жылдық қауіп расталды дегенді білдірмейді.')
    d.page();d.h('2 Жүз бетке арналған бөлу жоспары')
    plan=RULES['page_plan']
    d.table(['Беттер','Бөлім','Көлем'],[[str(a) if a==b else f'{a}–{b}',t,str(b-a+1)] for a,b,t,main in plan[:13]],[W*.15,W*.70,W*.15])
    d.p('Кіріспеден қорытындының соңына дейін: 11–60-беттер, яғни 50 бет. Алғашқы құжаттардың нақты ұзындығы алынған соң мазмұндағы беттер қайта есептеледі. Platonus есебіне бір бет бөлінуі жоспарлық болжам ғана; шынайы есептің бет саны өзгеше болуы мүмкін.','small')
    d.page();d.h('3 Қосымшалардың мазмұны')
    d.table(['Беттер','Қосымша','Көлем'],[[f'{a}–{b}',t,str(b-a+1)] for a,b,t,main in plan[13:]],[W*.15,W*.70,W*.15])
    d.p('Белгілер сөздігінде бастапқы айнымалы, санат, өлшем бірлігі, арнайы жауап, түрлендіру және интерфейс өрісі көрсетіледі. Толық нәтижелер кестесінде деректер жинағы, бөлу, үлгі көлемі, порог, салмақтау және белгісіздік түрі міндетті түрде жазылады.')
    d.p('Техникалық материалдар эксперименттердің сақталған файлдарынан алынған. Оларға жаңа тәжірибе жүргізілгендей түсініктеме қосылмайды. Пайдаланушының жеке медициналық жауаптары қосымшаларға енгізілмейді. Үлгі сценарийлер синтетикалық екені белгіленеді.')
    d.page();d.h('4 Рәсімдеу параметрлері')
    d.table(['Параметр','Талап және ережедегі орны'],[['Қағаз және басылым','A4, бір жақ бет; 10.5'],['Негізгі қаріп','Times New Roman, 14 pt, қалыпты; 10.5'],['Жоларалық интервал','Бір интервал; 10.5'],['Жиектер','Сол30 мм; оң10 мм; үст20 мм; аст25 мм; 10.6'],['Абзац','Бірінші жол шегінісі1.25 см; 10.6'],['Бет нөмірі','Араб цифры, төменгі орта; кіріспеден басылады; 10.10–10.12'],['Тарау','Жаңа беттен; нөмірлі атау, соңында нүкте жоқ; 10.14–10.15'],['Кестелер мен суреттер','Мәтінде сілтеме, нөмір, атау және дереккөзі; 10.16–10.18'],['Формулалар','Жеке жол, нөмір және белгілеулер түсіндірмесі; 10.19'],['Әдебиеттер','Кемінде30; [n] сілтемесі; алғашқы аталу реті; белсенді URL/DOI; 9.15 және10.20–10.22'],['Электрондық тапсыру','PDF, баспа нұсқамен бірдей; 10.24']],[W*.32,W*.68])
    d.p('Аннотация негізгі қазақша мәтіннен бөлек орыс және ағылшын тілдерінде дайындалады. Ереже 150–200 сөз көлемін көрсетеді (9.6). Қосымшалар ретімен аталып, әрқайсысы жаңа беттен басталады (10.23).','small')
    d.page();d.h('5 Кітаптармен және сілтемелермен жұмыс')
    d.p('Әдебиет каталогы оқуға арналған тексерілген үміткер дереккөздерді жинақтайды. Кітаптың библиографиялық мәліметін немесе мазмұнын тексеру оның барлық тарауы оқылды дегенді білдірмейді. Әр жазбада қолжетімділік пен тексеру шекарасы сақталған.')
    steps=[('1 Дереккөзді ашу','Керек тарауды заңды авторлық немесе баспа сілтемесімен ашу. Мақала тек аннотациямен тексерілсе, толық әдістемелік тұжырым шығармау.'),('2 Оқу жазбасын жасау','Қаралған бөлім мен нақты бетті, негізгі ойды және жобаға қатысын өз сөзіңмен жазу. Мәтінді тікелей аударып, өз ойың ретінде ұсынбау.'),('3 Сілтемені қою','Бірінші аталған дереккөз [1], келесісі [2] тәртібімен нөмірленеді. Каталогтағы B/P/D белгілері уақытша жұмыс кілттері.'),('4 Дәйексөзді ажырату','Сөзбе-сөз үзінді тырнақшада және тексерілген бетімен беріледі. Парафразға да сілтеме қойылады. Кітаптан ұзақ мәтінді көшіріп көлем толтыруға болмайды.'),('5 Нәтижені бөлек көрсету','Кітапта берілген теория, басқа мақаладағы нәтиже және осы жобада өлшенген метрика бөлек аталады. Біздің сандар reports файлдарымен салыстырылады.'),('6 Тізімді тексеру','Тізімге тек мәтінде пайдаланылған дереккөз кіреді. Әр URL/DOI ашылады. Веб-беттің баспа беті болмаған жағдайда бөлім атауы қолданылады; бет нөмірі ойдан қойылмайды.')]
    for title,body in steps:d.h(title,2);d.p(body)
    d.page();d.h('6 Авторлық жұмыс және ЖИ қолдануын көрсету')
    d.p('Ереженің 11.21–11.22-тармақтары ЖИ көмегін дерек іздеу, бағдарламалау, есептеу, жоспар және тілдік түзету үшін пайдалануға мүмкіндік береді. Нәтижені студент тексеруі, маңызды қолданылуын ашуы және зерттеу шешімдерін өзі түсіндіре алуы қажет.')
    d.p('11.23-тармақ дипломның толық немесе басым мәтінін, кіріспені, негізгі бөлімді, аннотацияны, қорытынды мен тұжырымдарды студент орнына автоматты жазуға тыйым салады. Сондықтан осы пакет дайын диплом тарауларын алмастырмайды. Бұрын жасалған қысқа диплом және қорғау файлдары авторлық өңдеу мен ережеге сәйкестендіруді қажет ететін ЖИ көмегімен дайындалған нобайлар ретінде қаралады.')
    d.p('11.25-тармаққа сәйкес ЖИ жасаған немесе елеулі өзгерткен материалдың жанында құрал мен қолданылу сипаты көрсетіледі. Осы пакет пен техникалық кестелер Codex көмегімен дайындалды. Студенттің жеке тексеруі әлі тіркелген жоқ; «студент тексерді» деп жалған белгі қойылмайды.')
    d.p('Декларациядағы «ЖИ қолданылмады» нұсқасын осы жұмысқа автоматты түрде қоюға болмайды. Нақты қолданылу мен студенттің тексеруін журналға тіркеп, декларацияны ереженің 8-қосымшасы бойынша толтыру қажет. Жүйенің тексеру ұпайына немесе ЖИ пайызына алдын ала кепілдік берілмейді.')
    d.table(['Студент толтыратын өріс','Не жазылады'],[['Оқылған еңбек','Атауы, нақты тарау/бет және оқылған күні'],['Тексерілген нәтиже','Файл/кесте, қайта есептеу жолы және қорытынды'],['Авторлық шешім','Өз таңдауың, негіздеме және қаралған балама'],['ЖИ көмегі','Құрал, нақты тапсырма, қолданылған бөлік'],['Жетекші ескертпесі','Ескерту және орындалған өзгеріс']],[W*.37,W*.63])
    d.page();d.h('7 Қолда бар дәлелдер және ашық мәселелер')
    b=read('brfss_data.json'); r=read('brfss_results.json');u=read('uci_results.json');v=read('verification.json')
    winner=next(x for x in r['full'] if x['name']==r['selection']['deployed_model'])
    d.table(['Тексерілген дерек','Сақталған мән'],[['BRFSS бастапқы файл',f"{b['raw_rows']:,} жол; {b['raw_columns']} баған".replace(',',' ')],['Нысанасы белгілі бақылаулар',f"{b['retained']:,}".replace(',',' ')],['Тәуелсіз тест',f"{b['test_n']:,}".replace(',',' ')],['Іріктелген модель',r['selection']['deployed_model']],['Тест ROC-AUC / AP',f"{winner['metrics']['roc_auc']:.4f} / {winner['metrics']['average_precision']:.4f}"],['Автоматты тексерулер',f"{v['automated_tests']['tests']} тест; қате0"],['Docker','Конфигурация бар; Engine қолжетімсіз болғандықтан іске қосылмаған']],[W*.48,W*.52])
    d.p('Толық техникалық аудитте UCI сыртқы кросс-валидациясының екі конфигурациялық іздеуін соңғы үш конфигурациялық қайта оқытудан ажырату керектігі көрсетілді. UCI үшін орташа және стандарттық ауытқу берілген; 95% сенімділік аралығы есептелмеген. Бұл тармақтар аяқталған тәжірибе ретінде жазылмайды.')
    d.p('BRFSS-тің жас кіші топтарында recall нөлге тең болатын жағдайлар бар. [0,0] bootstrap аралығы белгісіздік жоқ дегенді білдірмейді. Калибрлеудегі Brier айырмасы өте аз; статистикалық маңыздылығы тексерілген жоқ. Толық ескертпелер техникалық кестелерде берілген.')
    d.p('Келесі қадам: студенттің кіріспе, үш тараудағы талдау және қорытынды мәтінін әзірлеуі; дереккөздер мен есептерді тексеруі. Содан кейін тілдік өңдеу, сілтемелерді реттеу, 100 беттік беттеу және соңғы PDF тексеруі орындалады. Қазір 100 беттік дайын жұмыс пен университеттің қабылдауы туралы мәлімдеме жасалмайды.')
    d.save('ENU_100bet_zhospar_KZ')

def catalog():
    books=read('literature_books.json')['books'];papers=read('literature_papers.json')['sources'];docs=read('literature_software.json')['sources']
    d=Doc('Кітаптар мен ғылыми дереккөздердің оқу каталогы')
    d.p('Кітаптар мен ғылыми дереккөздер','title')
    d.p(f'Тексерілген оқу каталогы: {len(books)+len(papers)+len(docs)} жазба. {len(books)} кітап, {len(papers)} мақала және деректер құжаты, {len(docs)} бағдарламалық ресми анықтама. Тексерілген күні: 07.11.2026.')
    d.p('Мәртебесі: Codex көмегімен жиналған оқу және библиографиялық тексеру көмекшісі. Бұл тізім соңғы дипломда барлық дереккөз пайдаланылғанын білдірмейді. Студент қажетті бөлімдерді оқып, өз мәтініне сүйенген дереккөздерді ғана енгізеді. Төмендегі кілттер алғашқы аталу ретімен кейін қайта нөмірленеді.')
    d.p('Баспа беттері көрсетілсе, олардың тексеру деңгейі қоса беріледі. Мазмұн кестесіндегі бет аралығы нақты ой алынған бет орнына қолданылмайды. Веб-беттерде тұрақты бет нөмірі болмауы мүмкін. URL/DOI сілтемелері белсенді.','small')
    d.h('Кітаптар')
    for i,b in enumerate(books,1):
        d.h(f'B{i:02d} {b["title"]}',2);d.p(b['citation'],'small')
        primary_url=b.get('publisher_url') or b.get('official_url')
        d.link(primary_url)
        if b.get('official_url') and b.get('official_url')!=primary_url:d.link(b['official_url'])
        d.p('Оқу мақсаты: '+b.get('project_use','Көрсетілген бөлімдерді студент өзі оқиды.'),'small')
        sections=[]
        for s in b.get('verified_sections',[]):
            title=str(s.get('chapter',s.get('section','')))+' '+s.get('title','')
            if s.get('printed_pages'):title+='; беттер: '+str(s['printed_pages'])
            if s.get('printed_start_page') is not None:title+='; басталу беті: '+str(s['printed_start_page'])
            if s.get('content_read_pages'):title+='; нақты қаралған үзінді: '+str(s['content_read_pages'])
            if s.get('verified'):title+='; тексерілгені: '+str(s['verified'])
            sections.append(title.strip())
        if sections:d.p('Тексерілген бөлімдер: '+' | '.join(sections),'small')
        d.p('Қолжетімділік: '+b.get('legal_access','Тізілімдегі бастапқы жазбаны қараңыз.'),'small')
        if b.get('limitations'):d.p('Шектеуі: '+str(b['limitations']),'small')
        if b.get('pagination_warning'):d.p('Бет нөмірлері туралы ескерту: '+str(b['pagination_warning']),'small')
        qs=b.get('student_reading_questions', b.get('reading_questions',[]))
        if qs:d.p('Оқу сұрағы: '+str(qs[0]),'small')
    d.page();d.h('Мақалалар және бастапқы деректер')
    for p in papers:
        d.h(p['id']+' '+p['title'],2)
        citation=', '.join(p['authors'])+f". {p['title']}. "+(p['venue']+'. ' if p.get('venue') else '')+f"{p['year']}."
        for k in ['volume','issue','pages','article_number']:
            if p.get(k):citation+=f' {k}: {p[k]}.'
        d.p(citation,'small');d.link('https://doi.org/'+p['doi'] if p.get('doi') else p['url'])
        if p.get('year_note'):d.p('Жылы туралы ескерту: '+p['year_note'],'small')
        if p.get('full_text_url'):d.link(p['full_text_url'])
        d.p('Қолданылуы: '+p.get('suggested_section','')+'. '+p.get('summary_kz',''),'small')
        d.p('Тексеру: '+p.get('verification',''),'small')
        if p.get('verified_locators'):d.p('Орны: '+p['verified_locators'],'small')
        d.p('Шектеуі: '+p.get('limitation',''),'small')
    d.page();d.h('Бағдарламалық ресми анықтамалар')
    for x in docs:
        d.h(x['id']+' '+x['title'],2)
        d.p(x['publisher']+'. '+x['version']+'. Қаралған күні:07.11.2026.','small');d.link(x['url']);d.p(x['use_kz'],'small')
    d.p('Бұл сегіз жазба әдістердің ғылыми мақалалары мен кітаптарын алмастырмайды; нақты іске асыру интерфейсі мен нұсқасын анықтауға қызмет етеді. Кітап, мақала және веб-құжаттардың қайталанатын түсіндірмелерін дипломда негізсіз көбейту қажет емес.','small')
    d.save('ENU_Adabietter_katalogy_KZ')

if __name__=='__main__':
    guide();catalog()
    from pypdf import PdfReader
    for stem in ['ENU_100bet_zhospar_KZ','ENU_Adabietter_katalogy_KZ']:
        r=PdfReader(OUT/(stem+'.pdf'));print(stem,len(r.pages),'pages',sum(len((p.extract_text() or '').split()) for p in r.pages),'words')
