/** Merge separately verified literature without rewriting frozen research reports. */
export function withLiteratureAdditions(library, additions) {
  const result=structuredClone(library || {});
  result.papers=Array.isArray(result.papers)?result.papers:[];
  const all=[...(result.books || []),...result.papers,...(result.software || []),...(result.atherosclerosis?.records || [])];
  const doiKey=value=>String(value || '').trim().replace(/^(?:https?:\/\/(?:dx\.)?doi\.org\/|doi:\s*)/i,'').toLowerCase();
  const seenDOIs=new Set(all.map(record=>doiKey(record.doi)).filter(Boolean));
  const seenIDs=new Set(result.papers.map(record=>record.id).filter(Boolean));
  for (const record of additions?.records || []) {
    if (!record || typeof record!=='object' || !record.id || !record.title) continue;
    const doi=doiKey(record.doi);
    if ((doi && seenDOIs.has(doi)) || seenIDs.has(record.id)) continue;
    result.papers.push(structuredClone(record));
    if (doi) seenDOIs.add(doi);
    seenIDs.add(record.id);
  }
  result.counts={...result.counts,books:(result.books || []).length,papers:result.papers.length,
    software:(result.software || []).length,atherosclerosis:(result.atherosclerosis?.records || []).length};
  return result;
}
