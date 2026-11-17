"""Merge supplementary references without rewriting frozen experiment reports."""
from copy import deepcopy
import re


def with_literature_additions(library, additions):
    result = deepcopy(library or {})
    papers = result.get('papers')
    if not isinstance(papers, list):
        papers = []
        result['papers'] = papers
    archive = result.get('atherosclerosis') or {}
    records = ((result.get('books') or []) + papers + (result.get('software') or [])
               + (archive.get('records') or []))

    def doi_key(value):
        return re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)', '',
                      str(value or '').strip(), flags=re.I).lower()

    seen_dois = {doi_key(record.get('doi')) for record in records if doi_key(record.get('doi'))}
    seen_ids = {record.get('id') for record in papers if record.get('id')}
    for record in (additions or {}).get('records', []):
        if not isinstance(record, dict) or not record.get('id') or not record.get('title'):
            continue
        doi = doi_key(record.get('doi'))
        if (doi and doi in seen_dois) or record['id'] in seen_ids:
            continue
        papers.append(deepcopy(record))
        if doi:
            seen_dois.add(doi)
        seen_ids.add(record['id'])
    result['counts'] = dict(result.get('counts') or {}, books=len(result.get('books') or []),
                            papers=len(papers), software=len(result.get('software') or []),
                            atherosclerosis=len(archive.get('records') or []))
    return result
