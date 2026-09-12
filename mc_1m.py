"""Full 1M-path characterisation of every archetype. Writes data/synthetic_mc_1m.json."""
import runtime  # noqa: F401
import json, time
import synthetic_delistings as s

out = {}
t0 = time.time()
for a in s.ARCHETYPES:
    r = s.characterise(a, n_sims=1_000_000)
    out[a] = r
    print(f"  {a:<18} median {r['median']:>+7.1%}  mean {r['mean']:>+7.1%}  "
          f"p05 {r['p05']:>+7.1%}  p95 {r['p95']:>+7.1%}  "
          f"<-80% {r['worse_than_80']:>5.1%}  [{time.time()-t0:.0f}s]", flush=True)
json.dump(out, open("data/synthetic_mc_1m.json", "w"), indent=2)
print("  written to data/synthetic_mc_1m.json")
