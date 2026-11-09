# Planner quality vs canonical plan (qwen2.5:7b-instruct, recorded plans, 200 tasks)

| metric | value |
|---|---|
| usable plans | 187 / 200 |
| step-set precision (usable) | 0.496 |
| step-set recall (usable) | 0.515 |
| step-set F1 (usable) | 0.486 |
| step-set F1 (all plans, unusable = 0) | 0.455 |
| pairwise order agreement (usable) | 0.978 |
| plans needing zero repair | 0.250 |
| plans equal to canonical (names, order) | 0.000 |

Evidence class: measured offline on recorded replies (tests/data/v15_local_model_plans.jsonl); governance steps excluded on both sides.
