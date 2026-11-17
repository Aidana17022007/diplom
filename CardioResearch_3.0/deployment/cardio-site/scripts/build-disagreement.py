"""Aggregate fixed UCI OOF predictions without exporting observation IDs or profiles."""
import argparse
from collections import Counter
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import zipfile


def build_report(rows, names):
    if not rows or len(names) != len(set(names)) or len(names) < 2:
        raise ValueError('A nonempty aligned prediction matrix is required')
    learned = [i for i, name in enumerate(names) if name != 'Dummy']
    if not learned or len(learned) % 2 != 1:
        raise ValueError('Consensus requires an odd number of trained algorithms')
    ids = set()
    predictions, targets = [], []
    for row in rows:
        if row['row_id'] in ids or row['target'] not in ('0', '1'):
            raise ValueError('Invalid or duplicated observation')
        ids.add(row['row_id'])
        values = [float(row[name]) for name in names]
        if any(not math.isfinite(p) or not 0 <= p <= 1 for p in values):
            raise ValueError('Invalid probability')
        predictions.append([int(p >= .5) for p in values])
        targets.append(int(row['target']))
    n = len(rows)
    patterns = Counter((target, ''.join(map(str, pred))) for target, pred in zip(targets, predictions))
    model_stats = []
    for i, name in enumerate(names):
        tn = sum(y == 0 and p[i] == 0 for y, p in zip(targets, predictions))
        fp = sum(y == 0 and p[i] == 1 for y, p in zip(targets, predictions))
        fn = sum(y == 1 and p[i] == 0 for y, p in zip(targets, predictions))
        tp = sum(y == 1 and p[i] == 1 for y, p in zip(targets, predictions))
        model_stats.append({'name': name, 'baseline': name == 'Dummy', 'tn': tn, 'fp': fp, 'fn': fn, 'tp': tp})
    pairs = []
    for a in range(len(names)):
        pair_row = []
        for b in range(len(names)):
            counts = Counter((p[a] == y, p[b] == y) for y, p in zip(targets, predictions))
            pair_row.append({'both_correct': counts[True, True], 'both_wrong': counts[False, False],
                             'only_a_correct': counts[True, False], 'only_b_correct': counts[False, True],
                             'disagree': counts[True, False] + counts[False, True]})
        pairs.append(pair_row)
    votes = [sum(p[i] for i in learned) for p in predictions]
    return {'schema_version': 1, 'dataset': 'uci', 'evaluation': 'averaged_oof', 'n': n,
            'positive': sum(targets), 'threshold': .5, 'models': model_stats, 'pairs': pairs,
            'learned_indices': learned, 'summary': {
                'disagreement_n': sum(v not in (0, len(learned)) for v in votes),
                'unanimous_wrong_n': sum(all(p[i] != y for i in learned) for y, p in zip(targets, predictions)),
                'split_vote_n': sum(v in (len(learned)//2, len(learned)//2+1) for v in votes),
                'unanimous_correct_n': sum(all(p[i] == y for i in learned) for y, p in zip(targets, predictions))},
            'patterns': [{'target': y, 'votes': bits, 'n': count} for (y, bits), count in
                         sorted(patterns.items(), key=lambda item: (-item[1], item[0]))],
            'methods': {'threshold_rule': 'probability >= 0.5', 'summary_excludes': ['Dummy'],
                        'oof_repeats_per_observation': 2, 'refitted': False,
                        'limits': ['Averaged OOF outputs, not independent predictions from final saved artifacts.',
                                   'Agreement is descriptive; unanimous predictions can be wrong.',
                                   'A common 0.5 analysis threshold is used for all algorithms; no threshold is selected here.',
                                   'No observation identifiers, feature profiles or individual probabilities are exported.']}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--archive', type=Path)
    source.add_argument('--predictions', type=Path)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1]/'data/disagreement.json')
    args = parser.parse_args()
    if args.archive:
        with zipfile.ZipFile(args.archive) as archive:
            raw = archive.read('CardioResearch/reports/uci_oof_predictions.csv')
    else:
        raw = args.predictions.read_bytes()
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    names = [name for name in reader.fieldnames if name not in ('row_id', 'target')]
    report = build_report(list(reader), names)
    report['source'] = {'file': 'uci_oof_predictions.csv', 'sha256': hashlib.sha256(raw).hexdigest()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'n': report['n'], 'models': len(names), 'patterns': len(report['patterns']), **report['summary']}))


if __name__ == '__main__':
    main()
