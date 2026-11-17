import { PDFDocument, rgb } from 'pdf-lib';
import fontkit from '@pdf-lib/fontkit';

// This vocabulary mirrors cardio/i18n.py. Values come from validated model inputs;
// the report does not make a second prediction or fetch any remote resources.
const FIELD_KK = {
  age_group: 'Жас тобы', sex: 'Жынысы', bmi: 'Дене салмағының индексі', smoking: 'Темекі шегу',
  activity: 'Соңғы айдағы дене белсенділігі', diabetes: 'Қант диабеті туралы хабарланған ба?',
  hypertension: 'Қан қысымының жоғарылауы туралы хабарланған ба?',
  cholesterol: 'Холестериннің жоғарылауы туралы хабарланған ба?', general_health: 'Денсаулықтың жалпы бағасы',
  physical_days: 'Соңғы 30 күндегі дене жайсыздығы күндері',
  mental_days: 'Соңғы 30 күндегі эмоционалдық жайсыздық күндері', age: 'Жасы',
  cp: 'Кеудедегі ауырсыну түрі', trestbps: 'Тыныштықтағы қан қысымы, мм сын. бағ.',
  chol: 'Холестерин, мг/дл', fbs: 'Ашқарындағы глюкоза 120 мг/дл-ден жоғары', restecg: 'Тыныштықтағы ЭКГ',
  thalach: 'Жүктеме кезіндегі ең жоғары жүрек соғу жиілігі', exang: 'Жүктеме кезіндегі стенокардия',
  oldpeak: 'Жүктеме кезіндегі ST төмендеуі', slope: 'ST сегментінің көлбеуі',
  ca: 'Флюороскопияда көрінген тамырлар саны', thal: 'Таллий сынағының нәтижесі',
};
const OPTION_KK = {
  'Мужской': 'Ер', 'Женский': 'Әйел', 'Да': 'Иә', 'Нет': 'Жоқ', 'Каждый день': 'Күн сайын',
  'Иногда': 'Кейде', 'Курил(а) раньше': 'Бұрын шеккен',
  'Никогда регулярно не курил(а)': 'Ешқашан тұрақты шекпеген', 'Только при беременности': 'Тек жүктілік кезінде',
  'Преддиабет': 'Преддиабет', 'Пограничное повышение': 'Шекаралық жоғарылау', 'Отличное': 'Өте жақсы',
  'Очень хорошее': 'Жақсыдан жоғары', 'Хорошее': 'Жақсы', 'Удовлетворительное': 'Қанағаттанарлық',
  'Плохое': 'Нашар', '80 и старше': '80 және одан жоғары', 'Типичная стенокардия': 'Типтік стенокардия',
  'Атипичная стенокардия': 'Атиптік стенокардия', 'Неангинальная боль': 'Стенокардияға тән емес ауырсыну',
  'Бессимптомное течение': 'Симптомсыз ағым', 'Норма': 'Қалыпты', 'Изменения ST–T': 'ST–T өзгерістері',
  'Гипертрофия левого желудочка': 'Сол жақ қарынша гипертрофиясы', 'Восходящий': 'Жоғарылайтын',
  'Горизонтальный': 'Көлденең', 'Нисходящий': 'Төмендейтін', 'Фиксированный дефект': 'Тұрақты ақау',
  'Обратимый дефект': 'Қайтымды ақау',
};
const WORDS = {
  ru: {
    title: 'CardioResearch - отчёт модели', heading: 'Исследовательская оценка', dataset: 'Набор данных',
    model: 'Модель', version: 'Версия', estimate: 'Оценка модели', threshold: 'Порог', class: 'Класс по порогу',
    positive: 'Положительный', negative: 'Отрицательный', inputs: 'Введённые показатели', missing: 'Не указано',
    field: 'Показатель', value: 'Введённое значение', explanation: 'Объяснение базовой модели',
    contribution: 'Вклад, п.п.', units: 'п.п.', baseline: 'Фоновая оценка', raw: 'Базовая модель',
    limitations: 'Область применения и ограничения', page: 'Страница', continued: 'Продолжение',
    positiveNote: 'Показана вероятность положительного класса по модели. Решение получается при сравнении оценки с указанным порогом.',
    explanationNote: 'Приближённая оценка Шепли по перестановкам. Вклады относятся к вероятности базовой модели до дополнительной калибровки, если она применяется. Это статистическое объяснение модели, а не причинный эффект.',
    explanationSum: 'Фоновая оценка и сумма вкладов дают оценку базовой модели. Она может отличаться от итоговой откалиброванной оценки на первой странице.',
    methodCounts: (orders, background) => `${orders} перестановок и ${background} обучающих наблюдений для фоновой выборки.`,
    missingNote: 'Неуказанные показатели обработаны сохранённым алгоритмом заполнения пропусков, обученным на тренировочных данных. В отчёте сохранено исходное отсутствие ответа.',
    privacy: 'Ответы переданы на сервер для расчёта и обработаны временно. Приложение не сохраняет медицинские ответы.',
    footer: 'Исследовательский отчёт',
    disclaimer: {
      brfss: 'Исследовательский прототип. Оценка связи ответов анкеты с сообщённым инфарктом или стенокардией/коронарной болезнью, а не диагноз или прогноз будущего события. Не предназначен для назначения лечения.',
      uci: 'Исследовательский прототип. Классификация наличия коронарного заболевания по клиническим показателям Cleveland, а не подтверждённый диагноз или прогноз будущего события. Не предназначен для назначения лечения.',
    },
    population: {
      brfss: 'BRFSS 2023: самоотчётные ответы обследования США. Оценка не устанавливает причинность и не подтверждена для населения Казахстана.',
      uci: 'UCI Heart Disease: небольшой клинический набор Cleveland. Переносимость на другие центры и население Казахстана не подтверждена.',
    },
  },
  kk: {
    title: 'CardioResearch - модель есебі', heading: 'Зерттеу моделінің бағасы', dataset: 'Деректер жинағы',
    model: 'Модель', version: 'Нұсқа', estimate: 'Модель бағасы', threshold: 'Шек', class: 'Шек бойынша сынып',
    positive: 'Оң', negative: 'Теріс', inputs: 'Енгізілген көрсеткіштер', missing: 'Көрсетілмеген',
    field: 'Көрсеткіш', value: 'Енгізілген мән', explanation: 'Бастапқы модельдің түсіндірмесі',
    contribution: 'Үлес, пайыздық тармақ', units: 'пайыздық тармақ', baseline: 'Фондық баға', raw: 'Бастапқы модель',
    limitations: 'Қолданылу аясы және шектеулер', page: 'Бет', continued: 'Жалғасы',
    positiveNote: 'Модель бойынша оң сыныптың ықтималдығы көрсетілген. Шешім осы бағаны көрсетілген шекпен салыстыру арқылы алынады.',
    explanationNote: 'Алмастыру реттері бойынша Шепли үлесінің жуық есебі. Үлестер қосымша калибрлеуге дейінгі бастапқы модель ықтималдығына қатысты, егер калибрлеу қолданылса. Бұл себептік әсер емес, модельдің статистикалық түсіндірмесі.',
    explanationSum: 'Фондық баға мен үлестер қосындысы бастапқы модель бағасын береді. Ол бірінші беттегі соңғы калибрленген бағадан өзгеше болуы мүмкін.',
    methodCounts: (orders, background) => `${orders} алмастыру реті және фондық іріктемеге арналған ${background} оқыту бақылауы.`,
    missingNote: 'Көрсетілмеген мәндер оқыту деректерінде үйретілген сақталған алгоритм арқылы толтырылды. Есепте жауаптың бастапқы болмауы көрсетілген.',
    privacy: 'Жауаптар есептеу үшін серверге жіберіліп, уақытша өңделді. Қосымша медициналық жауаптарды сақтамайды.',
    footer: 'Зерттеу есебі',
    disclaimer: {
      brfss: 'Зерттеу прототипі. Сауалнама жауаптарының бұрын хабарланған инфаркт немесе стенокардия/коронарлық аурумен байланысын бағалайды. Бұл диагноз немесе болашақ оқиғаның болжамы емес. Ем тағайындауға арналмаған.',
      uci: 'Зерттеу прототипі. Cleveland клиникалық көрсеткіштері бойынша коронарлық аурудың бар-жоғын жіктейді. Бұл расталған диагноз немесе болашақ оқиғаның болжамы емес. Ем тағайындауға арналмаған.',
    },
    population: {
      brfss: 'BRFSS 2023: АҚШ сауалнамасындағы респонденттердің өз жауаптары. Баға себептілікті анықтамайды және Қазақстан халқы үшін расталмаған.',
      uci: 'UCI Heart Disease: Cleveland орталығының шағын клиникалық жинағы. Басқа орталықтарға және Қазақстан халқына қолдану мүмкіндігі расталмаған.',
    },
  },
};

function text(value) {
  return String(value ?? '').replace(/[\u0000-\u001f\u007f-\u009f]/g, ' ')
    .replace(/[\u2010-\u2015\u2212]/g, '-').replace(/\s+/g, ' ').trim();
}
function label(field, lang) { return lang === 'kk' ? FIELD_KK[field.name] || field.label : field.label; }
function displayValue(field, value, lang) {
  if (value == null) return WORDS[lang].missing;
  if (typeof value !== 'number' || !Number.isFinite(value)) throw new TypeError('PDF inputs must be validated numbers or null');
  if (field.kind !== 'category') return String(value);
  const option = field.options?.find(item => item.value === value);
  if (!option) throw new TypeError('PDF input contains an unknown category');
  return lang === 'kk' ? OPTION_KK[option.label] || option.label : option.label;
}

/**
 * Create a self-contained RU/KK report from an already computed prediction.
 * Compatible with a Worker: no filesystem, Node built-ins, network, or retained input state.
 * @param {{dataset:'brfss'|'uci', values:Object, lang?:'ru'|'kk', result:Object,
 * schema:Array|{fields:Array}, fontBytes:Uint8Array}} input
 * @returns {Promise<Uint8Array>}
 */
export async function buildPdf({ dataset, values, lang = 'ru', result, schema, fontBytes }) {
  if (!WORDS[lang] || !['brfss', 'uci'].includes(dataset)) throw new TypeError('Unsupported report language or dataset');
  const fields = Array.isArray(schema) ? schema : schema?.fields;
  if (!fields?.length || fields.length > 32) throw new TypeError('A bounded feature schema is required');
  if (!fontBytes?.byteLength || fontBytes.byteLength > 2 * 1024 * 1024) throw new TypeError('A bounded Unicode font is required');
  if (!result || !Number.isFinite(result.probability) || result.probability < 0 || result.probability > 1
      || !Number.isFinite(result.threshold) || result.threshold < 0 || result.threshold > 1) {
    throw new TypeError('A valid model probability and threshold are required');
  }
  if (result.explanation?.units && result.explanation.units !== 'raw_model_probability') {
    throw new TypeError('This report requires explanation contributions in raw model probability units');
  }
  const words = WORDS[lang];
  const inputRows = fields.map(field => [label(field, lang), displayValue(field, values?.[field.name], lang)]);
  const pdf = await PDFDocument.create();
  pdf.registerFontkit(fontkit);
  const font = await pdf.embedFont(fontBytes, { subset: true });
  pdf.setTitle(words.title); pdf.setAuthor('CardioResearch'); pdf.setCreator('CardioResearch');
  pdf.setSubject(`${dataset.toUpperCase()} - ${words.heading}`); pdf.setLanguage(lang === 'kk' ? 'kk-KZ' : 'ru-RU');
  const pageWidth = 595.28, pageHeight = 841.89, margin = 42, width = pageWidth - margin * 2;
  const color = { ink: rgb(0.09, 0.16, 0.22), muted: rgb(0.35, 0.41, 0.45), teal: rgb(0.02, 0.42, 0.39),
    line: rgb(0.85, 0.89, 0.89), light: rgb(0.94, 0.97, 0.97), white: rgb(1, 1, 1) };
  let page, y;
  const pages = [];
  function draw(value, x, baseline, size = 9.5, fill = color.ink) {
    page.drawText(text(value), { x, y: baseline, size, font, color: fill });
  }
  function wrap(value, maxWidth, size = 9.5) {
    const lines = []; let current = '';
    // Split exceptionally long tokens as well, so metadata cannot overflow a page.
    for (const word of text(value).split(' ')) {
      const candidate = current ? `${current} ${word}` : word;
      if (font.widthOfTextAtSize(candidate, size) <= maxWidth) { current = candidate; continue; }
      if (current) lines.push(current);
      current = '';
      for (const character of word) {
        if (current && font.widthOfTextAtSize(current + character, size) > maxWidth) {
          lines.push(current); current = '';
        }
        current += character;
      }
    }
    if (current) lines.push(current);
    return lines.length ? lines : [''];
  }
  function newPage() {
    page = pdf.addPage([pageWidth, pageHeight]); pages.push(page); y = pageHeight - margin;
    draw('CardioResearch', margin, y - 17, 21, color.teal);
    const datasetLabel = dataset === 'brfss' ? 'CDC BRFSS 2023' : 'UCI CLEVELAND';
    draw(datasetLabel, pageWidth - margin - font.widthOfTextAtSize(datasetLabel, 9), y - 12, 9, color.muted);
    y -= 34;
    page.drawLine({ start: { x: margin, y }, end: { x: pageWidth - margin, y }, color: color.line, thickness: 0.8 });
    y -= 25;
  }
  function ensure(height) { if (y - height < 66) newPage(); }
  function paragraph(value, { size = 9.5, fill = color.ink, after = 8, indent = 0 } = {}) {
    const lines = wrap(value, width - indent, size), height = size + 4;
    if (lines.length * height < pageHeight - margin - 130) ensure(lines.length * height);
    for (const line of lines) { ensure(height); draw(line, margin + indent, y, size, fill); y -= height; }
    y -= after;
  }
  function heading(value) { ensure(44); y -= 5; paragraph(value, { size: 13, fill: color.teal, after: 9 }); }
  function tableHeader(left, right, rightWidth) {
    ensure(35);
    page.drawRectangle({ x: margin, y: y - 24, width, height: 28, color: color.light });
    draw(left, margin + 10, y - 14, 9, color.muted);
    draw(right, margin + width - rightWidth + 10, y - 14, 9, color.muted); y -= 32;
  }
  function table(rows, { rightWidth = 176, headers = [words.field, words.value], signed = false, compact = false } = {}) {
    tableHeader(...headers, rightWidth);
    const size = compact ? 9 : 9.3, lineHeight = compact ? 12.5 : 13.3;
    for (const [left, right] of rows) {
      const leftLines = wrap(left, width - rightWidth - 22, size);
      const rightLines = wrap(right, rightWidth - 22, size);
      const rowHeight = Math.max(leftLines.length, rightLines.length) * lineHeight + (compact ? 9 : 13);
      if (y - rowHeight < 66) { newPage(); tableHeader(...headers, rightWidth); }
      leftLines.forEach((line, i) => draw(line, margin + 10, y - 10 - i * lineHeight, size));
      rightLines.forEach((line, i) => draw(line, margin + width - rightWidth + 10, y - 10 - i * lineHeight, size,
        signed && String(right).startsWith('+') ? color.teal : color.ink));
      y -= rowHeight;
      page.drawLine({ start: { x: margin, y }, end: { x: margin + width, y }, color: color.line, thickness: 0.5 });
      y -= compact ? 2 : 3;
    }
    y -= 9;
  }
  const percent = number => `${(number * 100).toFixed(1)}%`;
  newPage();
  paragraph(words.heading, { size: 17, after: 8 });
  paragraph(`${words.model}: ${text(result.model).slice(0, 100)}  |  ${words.version}: ${text(result.version).slice(0, 80)}`,
    { size: 9, fill: color.muted, after: 13 });
  const cardTop = y + 2;
  page.drawRectangle({ x: margin, y: cardTop - 74, width, height: 74, color: color.light });
  const cardColumns = [margin + 14, margin + width * 0.39, margin + width * 0.64];
  [words.estimate, words.threshold, words.class].forEach((word, i) => draw(word, cardColumns[i], cardTop - 18, 9, color.muted));
  draw(percent(result.probability), cardColumns[0], cardTop - 51, 25, color.teal);
  draw(result.threshold.toFixed(3), cardColumns[1], cardTop - 48, 19);
  draw(result.probability >= result.threshold ? words.positive : words.negative, cardColumns[2], cardTop - 46, 13);
  y = cardTop - 91;
  paragraph(words.positiveNote, { size: 9, fill: color.muted, after: 9 });
  heading(words.inputs); table(inputRows);
  if (fields.some(field => values?.[field.name] == null)) paragraph(words.missingNote, { size: 8.8, fill: color.muted });

  const explanation = result.explanation;
  if (explanation?.contributions?.length) {
    const byName = new Map(fields.map(field => [field.name, field]));
    const contributionRows = explanation.contributions.slice(0, 32).map(item => {
      const field = byName.get(item.feature);
      if (!field || !Number.isFinite(item.value)) throw new TypeError('Explanation must match the feature schema');
      const signed = (item.value * 100).toFixed(2);
      return [label(field, lang), `${item.value >= 0 ? '+' : ''}${signed}`];
    });
    newPage(); heading(words.explanation);
    paragraph(words.explanationNote, { size: 9, fill: color.muted, after: 9 });
    const orders = explanation.permutations ?? explanation.n_permutations;
    const background = explanation.background_size ?? explanation.background_n;
    if (Number.isInteger(orders) && orders > 0 && Number.isInteger(background) && background > 0) {
      paragraph(words.methodCounts(orders, background), { size: 8.8, fill: color.muted, after: 8 });
    }
    if (Number.isFinite(explanation.baseline) && Number.isFinite(explanation.raw_probability)) {
      paragraph(`${words.baseline}: ${percent(explanation.baseline)}  |  ${words.raw}: ${percent(explanation.raw_probability)}`,
        { size: 10, after: 9 });
    }
    table(contributionRows, { rightWidth: 178, headers: [words.field, words.contribution], signed: true, compact: true });
    paragraph(words.explanationSum, { size: 8.8, fill: color.muted });
  }
  heading(words.limitations);
  paragraph(words.disclaimer[dataset], { size: 9.2 });
  paragraph(words.population[dataset], { size: 8.8, fill: color.muted });
  paragraph(words.privacy, { size: 8.5, fill: color.muted });
  for (let index = 0; index < pages.length; index++) {
    page = pages[index];
    page.drawLine({ start: { x: margin, y: 49 }, end: { x: pageWidth - margin, y: 49 }, color: color.line, thickness: 0.7 });
    draw(`CardioResearch  |  ${words.footer}`, margin, 33, 8, color.muted);
    const pageLabel = `${words.page} ${index + 1} / ${pages.length}`;
    draw(pageLabel, pageWidth - margin - font.widthOfTextAtSize(pageLabel, 8), 33, 8, color.muted);
  }
  return pdf.save({ useObjectStreams: true });
}
