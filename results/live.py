#!/usr/bin/env python3
"""Live ASCII monitor for benchmark progress."""
import json, time, sys
from pathlib import Path

RESULTS_DIR = Path(__file__).resolve().parent
DS_ORDER = ['mmlu-e','triage','truthfulqa','medbullets','medcalc','metamedqa','mmlu-m','pubmedqa','bbq','casehold','mmlu-s','mmlupro-s']
DS_SHORT = ['MLE','TRI','TQA','MBl','MCl','MMQ','MLM','PMQ','BBQ','CSH','MLS','MLP']

def snap():
    data = {}
    for f in sorted(RESULTS_DIR.glob('*.json')):
        if f.name == 'summary.json': continue
        try: d = json.load(open(f))
        except: continue
        model = d['model'].split('/')[-1]
        r = d.get('hyperparameters', {}).get('reasoning')
        if r is True: model += ' +r'
        elif r is False: model += ' -r'
        ds = d['dataset_id']
        n = len(d.get('answers', []))
        t = d['total']
        acc = d['accuracy'] if n >= t else None
        data.setdefault(model, {})[ds] = (acc, n, t)
    return data

for _ in range(40):  # ~10 min
    data = snap()
    models = sorted(data.keys())
    if not models:
        print('No results yet...'); sys.stdout.flush()
        time.sleep(15); continue

    nw = max(len(m) for m in models) + 1
    lines = []
    lines.append(f'\nEdgeCase  {time.strftime("%H:%M:%S")}')
    lines.append(' ' * nw + ''.join(f'{s:>5}' for s in DS_SHORT) + '  AVG   #')
    lines.append(' ' * nw + '-' * 70)
    for m in models:
        row = f'{m:<{nw}}'
        accs = []
        for ds in DS_ORDER:
            if ds not in data[m]:
                row += '    .'
            else:
                acc, n, t = data[m][ds]
                if acc is not None:
                    row += f'{acc:4.0f}%'
                    accs.append(acc)
                else:
                    pct = int(n / t * 100) if t else 0
                    row += f' {pct:2d}%%'
        if accs:
            row += f' {sum(accs)/len(accs):4.1f}%'
        else:
            row += '     '
        done = sum(1 for ds in DS_ORDER if ds in data[m] and data[m][ds][0] is not None)
        row += f' {done:>2}/12'
        lines.append(row)
    total = sum(len(v) for v in data.values())
    comp = sum(1 for m in models if all(ds in data[m] and data[m][ds][0] is not None for ds in DS_ORDER))
    lines.append(f'{len(models)} models | {total} files | {comp} complete')
    print('\n'.join(lines))
    sys.stdout.flush()
    time.sleep(15)
