import json, os, time

RESULTS_DIR = "/home/robot/sites/edgecase/results"
DATASETS = ["bbq","casehold","medbullets","medcalc","metamedqa","mmlu-e","mmlu-m","mmlupro-s","mmlu-s","pubmedqa","triage","truthfulqa"]
DS_SHORT = ["BBQ","CASE","MEDB","MCAL","MMQA","ML-E","ML-M","MLP ","ML-S","PUBM","TRIA","TRQA"]

models = {}
for f in os.listdir(RESULTS_DIR):
    if not f.endswith(".json"): continue
    parts = f.replace(".json","").split("__")
    if len(parts) < 2: continue
    model, ds = parts[0], parts[1]
    try:
        d = json.load(open(os.path.join(RESULTS_DIR, f)))
        models.setdefault(model, {})[ds] = (len(d.get("answers",[])), d.get("total",0), d.get("accuracy",0))
    except:
        pass

model_names = sorted(models.keys())
short_names = [m.split("_")[-1][:16] for m in model_names]

def bar(done, total):
    if total == 0: return "  ??  "
    pct = done / total
    filled = int(pct * 6)
    if done == total: return "\u2588"*6
    elif pct > 0: return "\u2588"*filled + "\u2591"*(6-filled)
    else: return "\u2591"*6

now = time.strftime("%H:%M:%S")
print(f"  BENCHMARK MONITOR  {now}")
print()
hdr = "      "
for s in short_names:
    hdr += " | " + s.center(22)
print(hdr)
sep = "------"
for _ in model_names:
    sep += "-+------------------------"
print(sep)

td = ta = 0
md = {m:0 for m in model_names}
mt = {m:0 for m in model_names}

for i, ds in enumerate(DATASETS):
    row = DS_SHORT[i].rjust(6)
    for m in model_names:
        if ds in models[m]:
            done, tot, acc = models[m][ds]
            pct = 100*done//tot if tot else 0
            b = bar(done, tot)
            if done == tot:
                cell = f" | {b} {acc:5.1f}% done       "
            else:
                cell = f" | {b} {done:>4d}/{tot:<4d} {pct:>3d}%  "
            row += cell
            td += done; ta += tot
            md[m] += done; mt[m] += tot
        else:
            row += " | " + "\u2591"*6 + "      ---        "
    print(row)

print(sep)
trow = " TOTAL"
for m in model_names:
    d2 = md[m]; t2 = mt[m]
    p2 = 100*d2//t2 if t2 else 0
    st = "DONE" if d2==t2 and t2>0 else f"{p2}%"
    trow += f" |  {d2:>5d}/{t2:<5d}  {st:>8s}  "
print(trow)
gp = 100*td//ta if ta else 0
print(f"\n  Overall: {td}/{ta} ({gp}%)")
