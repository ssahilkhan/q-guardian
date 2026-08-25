# Q-Guardian Dataset Manifest

Generated: 2026-08-24T05:52:09.580437+00:00

| Dataset | Present | Samples | Malicious | Benign | Purpose |
|---|---|---:|---:|---:|---|
| prompt_injections | yes | 662 | 263 | 399 | control training pool (in-domain prompt injections) |
| benchmark_prompts | yes | 62 | 32 | 30 | small held-out QA smoke set |
| trustair_jailbreaks | yes | 1405 | 1405 | 0 | diverse training arm A/D (real-user jailbreaks, label=jailbreak:true) |
| trustair_regular | yes | 3500 | 0 | 3500 | diverse benign pool (capped at 2000 when building arms) |
| jailbreakv | yes | 5900 | 5900 | 0 | diverse training arm B/D (seeded 2000-sample subset, seed=42) |
| harmful_behaviors_train | yes | 416 | 416 | 0 | diverse training arm C/D (unlabeled rows; malicious by source, contamination-filtered at arm build time) |
| harmful_behaviors_test | yes | 104 | 104 | 0 | diverse training arm C/D (unlabeled rows; malicious by source, contamination-filtered at arm build time) |
| arm_control | yes | 2425 | 162 | 2263 | control training arm (2425 samples) |
| arm_a | yes | 3767 | 1504 | 2263 | training-diversity experiment arm A |
| arm_b | yes | 4425 | 2162 | 2263 | training-diversity experiment arm B |
| arm_c | yes | 2927 | 664 | 2263 | training-diversity experiment arm C |
| arm_d | yes | 6269 | 4006 | 2263 | DIVERSE training arm D (production retrain candidate) |
| split_train | yes | 2425 | 162 | 2263 | frozen internal train split |
| split_validation | yes | 110 | 41 | 69 | calibration + threshold selection ONLY |
| split_test | yes | 116 | 60 | 56 | internal test (evaluation only, never fitted) |
| split_external_eval_jbb | yes | 200 | 100 | 100 | EXTERNAL held-out evaluation (never fitted/selected on) |

## Benchmark registry

- `advbench` — gated (needs HF_TOKEN)
- `agentdojo` — gated (needs HF_TOKEN)
- `cyberseceval-prompt-injections` — gated (needs HF_TOKEN)
- `deepset-prompt-injections` — public
- `dolly-benign` — public
- `harmbench-behaviors` — gated (needs HF_TOKEN)
- `hex-phi` — gated (needs HF_TOKEN)
- `jailbreakbench-attacks` — gated (needs HF_TOKEN)
- `jbb-behaviors` — public
- `pal` — gated (needs HF_TOKEN)
- `wildjailbreak` — gated (needs HF_TOKEN)

## Notes

- Gated benchmark datasets (wildjailbreak, harmbench-behaviors, advbench, hex-phi, pal, agentdojo, cyberseceval-prompt-injections, jailbreakbench-attacks) require accepting Hub terms and setting the HF_TOKEN environment variable; they are NOT downloaded here.
- No credentials are stored by this tool.
