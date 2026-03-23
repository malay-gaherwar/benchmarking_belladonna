import json, os, time, sys

RESULTS_DIR = '/home/robot/sites/edgecase/results'
DATASETS = ['bbq','casehold','medbullets','medcalc','metamedqa','mmlu-e','mmlu-m','mmlupro-s','mmlu-s','pubmedqa','triage','truthfulqa']
DS_SHORT = ['BBQ','CASE','MEDB','MCAL','MMQA','ML-E','ML-M','MLP','ML-S','PUBM','TRIA','TRQA']

def load():
    models = {}
    for f in os.listdir(RESULTS_DIR):
        if not f.endswith('.json') or f == 'monitor.py': continue
        parts = f.replace('.json','').split('__')
        if len(parts) != 2: continue
        model, ds = parts
        try:
            d = json.load(open(os.path.join(RESULTS_DIR, f)))
            models.setdefault(model, {})[ds] = (len(d.get('answers',[])), d.get('total',0), d.get('accuracy',0))
        except: pass
    return models

def bar(done, total, width=6):
    if total == 0: return '  ??  '
    pct = done / total
    filled = int(pct * width)
    if done == total:
        return f'\033[32m{"█"*width}\033[0m'
    elif pct > 0:
        return f'\033[33m{"█"*filled}{"░"*(width-filled)}\033[0m'
    else:
        return '░' * width

def render(models):
    model_names = sorted(models.keys())
    short_names = []
    for m in model_names:
        s = m.split('_')[-1] if '_' in m else m
        short_names.append(s[:16])

    # Header
    print(f'\033[1m{"DATASET":>6s}', end='')
    for s in short_names:
        print(f' │ {s:^22s}', end='')
    print('\033[0m')
    print('──────', end='')
    for _ in model_names:
        print('─┼────────────────────────', end='')
    print()

    total_done = 0
    total_all = 0
    model_done = {m: 0 for m in model_names}
    model_total = {m: 0 for m in model_names}

    for i, ds in enumerate(DATASETS):
        print(f'{DS_SHORT[i]:>6s}', end='')
        for m in model_names:
            if ds in models[m]:
                done, tot, acc = models[m][ds]
                pct = 100*done//tot if tot else 0
                b = bar(done, tot)
                if done == tot:
                    print(f' │ {b} {acc:5.1f}% ✓      ', end='')
                else:
                    print(f' │ {b} {done:>4d}/{tot:<4d} {pct:>3d}% ', end='')
                total_done += done
                total_all += tot
                model_done[m] += done
                model_total[m] += tot
            else:
                print(f' │ {"░"*6} {"---":^15s} ', end='')
                # still count total for missing
        print()

    print('──────', end='')
    for _ in model_names:
        print('─┼────────────────────────', end='')
    print()

    print(f'{"TOTAL":>6s}', end='')
    for m in model_names:
        d = model_done[m]
        t = model_total[m]
        p = 100*d//t if t else 0
        status = '✓ DONE' if d == t and t > 0 else f'{p}%'
        print(f' │ {d:>5d}/{t:<5d}   {status:>8s}  ', end='')
    print()
    
    grand_pct = 100*total_done//total_all if total_all else 0
    print(f'\n  Overall: {total_done}/{total_all} ({grand_pct}%)\n')

while True:
    os.system('clear')
    print(f'\033[1m  BENCHMARK MONITOR\033[0m  {time.strftime("%H:%M:%S")}\n')
    models = load()
    if models:
        render(models)
    else:
        print('  No results found yet...')
    time.sleep(5)
