# Q-Guardian External Dataset Study Manifest
Generated: 2026-08-25T04:51:58.226344+00:00

## Study Design
- Primary External: jbb-behaviors (READY)
- Independent External: wildjailbreak (NEEDS HF_TOKEN)

## Datasets
| Dataset | Status | Samples | Role | Token |
|---|---|---|---|---|
| jbb-behaviors | AVAILABLE | 200 | PRIMARY EXTERNAL EVALUATION | No |
| deepset-prompt-injections | AVAILABLE | 662 | TRAINING / IN-DOMAIN | No |
| dolly-benign | PARTIAL - HF server 502 | 15000 | BENIGN CORPUS ONLY | No |
| trustair_jailbreaks | AVAILABLE | 1405 | TRAINING ARM A/D | No |
| trustair_regular | AVAILABLE | 3500 | TRAINING BENIGN POOL | No |
| jailbreakv | AVAILABLE | 5900 | TRAINING ARM B/D | No |
| harmful_behaviors_train | AVAILABLE | 416 | TRAINING ARM C/D | No |
| harmful_behaviors_test | AVAILABLE | 104 | TRAINING ARM C/D | No |
| wildjailbreak | GATED - NEEDS HF_TOKEN | ~5000+ | CANDIDATE PRIMARY EXTERNAL DATASET | Yes |
| harmbench-behaviors | GATED - NEEDS HF_TOKEN | ~500+ | CANDIDATE EXTERNAL DATASET | Yes |
| advbench | GATED - NEEDS HF_TOKEN | ~500+ | CANDIDATE EXTERNAL DATASET | Yes |
| hex-phi | GATED - NEEDS HF_TOKEN | ~1000+ | CANDIDATE EXTERNAL DATASET | Yes |
| pal | GATED - NEEDS HF_TOKEN | ~1000+ | CANDIDATE EXTERNAL DATASET | Yes |
| agentdojo | GATED - NEEDS HF_TOKEN | ~1000+ | CANDIDATE EXTERNAL DATASET | Yes |
| cyberseceval-prompt-injections | GATED - NEEDS HF_TOKEN | ~1000+ | CANDIDATE EXTERNAL DATASET | Yes |
| jailbreakbench-attacks | GATED - NEEDS HF_TOKEN | ~1000+ | CANDIDATE EXTERNAL DATASET | Yes |
| advbench | GATED - NEEDS HF_TOKEN | ~500+ | CANDIDATE EXTERNAL DATASET | Yes |

## Gaps
- No second independent external dataset currently available without HF_TOKEN
- dolly-benign is benign-only (cannot evaluate malicious detection)
- deepset-prompt-injections used in training (not independent)
- Training diversity data (trustair, jailbreakv, harmful_behaviors) used in arm_d training (not independent)

## Recommendation
Obtain HF_TOKEN for wildjailbreak (MIT license) to enable rigorous cross-dataset generalization study with two independent external datasets.