from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
REPORTS = ROOT / 'reports'
MODELS = ROOT / 'models'
DOWNLOADS = Path(os.environ.get('CARDIO_DATA_SOURCE', str(Path.home() / 'Downloads')))
SEED = 20261107
for folder in [DATA / 'raw', DATA / 'processed', REPORTS / 'figures', MODELS]:
    folder.mkdir(parents=True, exist_ok=True)

AGE_LABELS = ['18–24','25–29','30–34','35–39','40–44','45–49','50–54','55–59','60–64','65–69','70–74','75–79','80 и старше']
def category(name, label, options, source, group):
    return dict(name=name,label=label,kind='category',options=[dict(value=k,label=v) for k,v in options],source=source,group=group)
def number(name,label,low,high,source,group,step=1):
    return dict(name=name,label=label,kind='number',min=low,max=high,step=step,source=source,group=group)

BRFSS_FIELDS = [
    category('age_group','Возрастная группа',list(enumerate(AGE_LABELS,1)),'_AGEG5YR','О себе'),
    category('sex','Пол',[(1,'Мужской'),(2,'Женский')],'SEXVAR','О себе'),
    number('bmi','Индекс массы тела',1,99.99,'_BMI5 / 100','О себе',0.1),
    category('smoking','Курение',[(1,'Каждый день'),(2,'Иногда'),(3,'Курил(а) раньше'),(4,'Никогда регулярно не курил(а)')],'_SMOKER3','Образ жизни'),
    category('activity','Физическая активность за последний месяц',[(1,'Да'),(2,'Нет')],'EXERANY2','Образ жизни'),
    category('diabetes','Сообщали ли вам о диабете?',[(1,'Да'),(2,'Только при беременности'),(3,'Нет'),(4,'Преддиабет')],'DIABETE4','Состояние здоровья'),
    category('hypertension','Сообщали ли вам о повышенном давлении?',[(1,'Да'),(2,'Только при беременности'),(3,'Нет'),(4,'Пограничное повышение')],'BPHIGH6','Состояние здоровья'),
    category('cholesterol','Сообщали ли вам о высоком холестерине?',[(1,'Да'),(2,'Нет')],'TOLDHI3','Состояние здоровья'),
    category('general_health','Общая оценка здоровья',[(1,'Отличное'),(2,'Очень хорошее'),(3,'Хорошее'),(4,'Удовлетворительное'),(5,'Плохое')],'GENHLTH','Самочувствие'),
    number('physical_days','Дней плохого физического самочувствия за 30 дней',0,30,'PHYSHLTH','Самочувствие'),
    number('mental_days','Дней плохого эмоционального самочувствия за 30 дней',0,30,'MENTHLTH','Самочувствие'),
]
UCI_FIELDS = [
    number('age','Возраст',18,100,'age','Основные показатели'),
    category('sex','Пол',[(0,'Женский'),(1,'Мужской')],'sex','Основные показатели'),
    category('cp','Тип боли в груди',[(1,'Типичная стенокардия'),(2,'Атипичная стенокардия'),(3,'Неангинальная боль'),(4,'Бессимптомное течение')],'cp','Клинические показатели'),
    number('trestbps','Давление в покое, мм рт. ст.',60,260,'trestbps','Основные показатели'),
    number('chol','Холестерин, мг/дл',50,700,'chol','Основные показатели'),
    category('fbs','Глюкоза натощак выше 120 мг/дл',[(0,'Нет'),(1,'Да')],'fbs','Клинические показатели'),
    category('restecg','ЭКГ в покое',[(0,'Норма'),(1,'Изменения ST–T'),(2,'Гипертрофия левого желудочка')],'restecg','Клинические показатели'),
    number('thalach','Максимальная ЧСС при нагрузке',50,230,'thalach','Нагрузочная проба'),
    category('exang','Стенокардия при нагрузке',[(0,'Нет'),(1,'Да')],'exang','Нагрузочная проба'),
    number('oldpeak','Депрессия ST при нагрузке',0,10,'oldpeak','Нагрузочная проба',0.1),
    category('slope','Наклон сегмента ST',[(1,'Восходящий'),(2,'Горизонтальный'),(3,'Нисходящий')],'slope','Нагрузочная проба'),
    category('ca','Число сосудов на флюороскопии',[(0,'0'),(1,'1'),(2,'2'),(3,'3')],'ca','Клинические показатели'),
    category('thal','Результат таллиевого теста',[(3,'Норма'),(6,'Фиксированный дефект'),(7,'Обратимый дефект')],'thal','Клинические показатели'),
]
SCHEMAS = {'brfss':BRFSS_FIELDS,'uci':UCI_FIELDS}
DISCLAIMER = 'Исследовательский прототип. Оценка связи анкеты с зарегистрированным заболеванием, а не диагноз или прогноз будущего события. Не предназначен для назначения лечения.'
