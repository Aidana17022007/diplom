/** Saved Docker evidence only confirms the application when its release matches. */
export function dockerQualityLimit(passport){
 const check=passport?.checks?.docker??{};
 let status=passport?.version_match===true?check.status:'not_verified';
 if(!['passed','failed'].includes(status))status='not_verified';
 const details={
  passed:'Сохранённый отчёт подтверждает сборку Docker и запуск моделей; полный набор тестов внутри контейнера не запускался.',
  failed:'В сохранённой проверке Docker зафиксирована ошибка.',
  not_verified:'Нет подтверждённой сборки и запуска Docker для этой версии приложения.',
 };
 return {id:'docker',title:'Контейнерный запуск',detail:details[status],status,report_file:check.report_file??null,report_sha256:check.report_sha256??null};
}
