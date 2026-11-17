/** Exact inference from fitted Python artifacts. No training or synthetic model. */
const compiled = new WeakMap();

export class ModelInputError extends Error {
  constructor(status, detail) {
    super(typeof detail === 'string' ? detail : detail.message || 'Invalid input');
    this.name = 'ModelInputError'; this.status = status; this.detail = detail;
  }
}

function modelFor(models, dataset) {
  const model = models.datasets?.[dataset];
  if (!model || !['brfss', 'uci'].includes(dataset)) throw new ModelInputError(400, 'Неизвестный набор данных');
  return model;
}

function prepare(model) {
  if (compiled.has(model)) return compiled.get(model);
  const n = model.preprocessing.numeric, c = model.preprocessing.categorical;
  const info = {
    numeric: n.names.map((name, i) => ({index:model.features.indexOf(name), fill:n.fill[i], mean:n.mean[i], scale:n.scale[i]})),
    categorical: c.names.map((name, i) => ({index:model.features.indexOf(name), fill:c.fill[i], categories:c.categories[i]})),
  };
  compiled.set(model, info); return info;
}

function absent(value) { return value === null || value === undefined || Number.isNaN(value); }

function transform(model, row) {
  const info = prepare(model), result = new Float64Array(model.preprocessing.output_width);
  let column = 0;
  for (const item of info.numeric) {
    const value = absent(row[item.index]) ? item.fill : row[item.index];
    result[column++] = (value - item.mean) / item.scale;
  }
  for (const item of info.categorical) {
    const value = absent(row[item.index]) ? item.fill : row[item.index];
    for (const category of item.categories) result[column++] = value === category ? 1 : 0;
  }
  // ForestClassifier predicts on float32 after preprocessing, including scaled numbers.
  if (model.estimator.type === 'random_forest') for (let i=0; i<result.length; i++) result[i] = Math.fround(result[i]);
  return result;
}

function logistic(score) { return 1 / (1 + Math.exp(-score)); }

function rawFromRow(model, row) {
  const x = transform(model, row), estimator = model.estimator;
  if (estimator.type === 'logistic_regression') {
    let score = estimator.intercept;
    for (let i=0; i<x.length; i++) score += x[i] * estimator.coef[i];
    return logistic(score);
  }
  if (estimator.type === 'random_forest') {
    let probability = 0;
    for (const tree of estimator.trees) {
      let node = 0;
      while (tree.left[node] !== -1) {
        const value = x[tree.feature[node]];
        const goLeft = Number.isNaN(value) ? Boolean(tree.missing_go_to_left[node]) : value <= tree.threshold[node];
        node = goLeft ? tree.left[node] : tree.right[node];
      }
      probability += tree.positive[node];
    }
    return probability / estimator.trees.length;
  }
  throw new Error('Unsupported exported estimator');
}

function rowFor(model, values) { return model.features.map(name => values[name] ?? null); }

export function validateValues(models, dataset, values) {
  const model = modelFor(models, dataset);
  if (!values || typeof values !== 'object' || Array.isArray(values)) throw new ModelInputError(422, {message:'Проверьте формат запроса',errors:[{field:'values',label:'Анкета',message:'Требуется объект показателей'}]});
  const names = new Set(model.features), errors = [], clean = {};
  for (const name of Object.keys(values)) if (!names.has(name)) errors.push({field:name,label:name,message:'Неизвестное поле'});
  for (const field of model.schema) {
    const value = values[field.name];
    if (value === null || value === undefined) { clean[field.name] = null; continue; }
    const invalid = message => errors.push({field:field.name,label:field.label,message});
    if (typeof value !== 'number' || !Number.isFinite(value)) { invalid('Требуется конечное число, а не текст или логическое значение'); continue; }
    if (field.kind === 'category' && !field.options.some(option => option.value === value)) invalid('Выберите допустимую категорию');
    else if (field.kind === 'number' && (value < field.min || value > field.max)) invalid(`Допустимый диапазон: ${field.min}–${field.max}`);
    else if (field.kind === 'number' && field.step === 1 && !Number.isInteger(value)) invalid('Требуется целое число');
    clean[field.name] = value;
  }
  if (errors.length) throw new ModelInputError(422, {message:'Проверьте введённые показатели',errors});
  if (Object.values(clean).filter(value => value !== null).length < 3) throw new ModelInputError(422, {message:'Заполните минимум три показателя. Остальные можно оставить неизвестными.',errors:[{field:'values',label:'Анкета',message:'Заполнено меньше трёх показателей'}]});
  return clean;
}

/** Low-level parity function: preprocessing handles missing and unseen categories. */
export function rawProbability(models, dataset, values) {
  const model = modelFor(models, dataset);
  return rawFromRow(model, rowFor(model, values));
}

export function predictProbability(models, dataset, values) {
  const model = modelFor(models, dataset), raw = rawFromRow(model, rowFor(model, values));
  if (!model.calibrator) return raw;
  const cal = model.calibrator, p = Math.min(cal.clip[1], Math.max(cal.clip[0], raw));
  return logistic(cal.intercept + cal.coef[0] * Math.log(p / (1-p)));
}

export function explainPrediction(models, dataset, values) {
  const model = modelFor(models, dataset), target = rowFor(model, values);
  const background = model.shap.background, width = model.features.length;
  const cache = new Map(), contributions = new Float64Array(width);
  // A coalition is independent of the path used to reach it; caching preserves
  // the same estimator while avoiding repeated forest evaluations.
  function coalition(mask) {
    if (cache.has(mask)) return cache.get(mask);
    let sum = 0;
    for (const base of background) {
      const row = base.map((value, i) => mask & (1 << i) ? target[i] : value);
      sum += rawFromRow(model, row);
    }
    const mean = sum / background.length; cache.set(mask, mean); return mean;
  }
  const baseline = coalition(0);
  for (const order of model.shap.orders) {
    let mask = 0, previous = baseline;
    for (const feature of order) {
      mask |= (1 << feature);
      const current = coalition(mask); contributions[feature] += current - previous; previous = current;
    }
  }
  const items = model.features.map((feature, i) => ({feature,value:contributions[i]/model.shap.orders.length}));
  return {method:model.shap.method,units:model.shap.units,baseline,raw_probability:rawFromRow(model,target),
    permutations:model.shap.orders.length,background_size:background.length,
    contributions:items.sort((a,b) => Math.abs(b.value)-Math.abs(a.value)),
    note:models.localization.report_text.ru.explanation_note};
}

export function predictPayload(models, request) {
  if (!request || typeof request !== 'object' || Array.isArray(request)) throw new ModelInputError(422,'Проверьте формат запроса');
  if (Object.keys(request).some(key => !['dataset','values','explain','lang'].includes(key))) throw new ModelInputError(422,'Неизвестное поле запроса');
  const dataset = request.dataset === undefined ? 'brfss' : request.dataset;
  const lang = request.lang === undefined ? 'ru' : request.lang;
  const explain = request.explain === undefined ? true : request.explain;
  if (!['ru','kk'].includes(lang) || typeof explain !== 'boolean' || typeof dataset !== 'string') throw new ModelInputError(422,'Неверная структура или тип данных запроса');
  const model = modelFor(models,dataset), clean = validateValues(models,dataset,request.values);
  const probability = predictProbability(models,dataset,clean);
  const result = {dataset,model:model.name,probability,threshold:model.threshold,positive:probability>=model.threshold,
    missing_fields:model.features.filter(name => clean[name] === null),
    disclaimer:models.localization.disclaimers[lang][dataset],version:model.version};
  if (explain) result.explanation = explainPrediction(models,dataset,clean);
  return result;
}
