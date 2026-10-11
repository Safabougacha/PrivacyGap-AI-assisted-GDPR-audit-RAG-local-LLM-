# Evaluation

*2026-10-11 17:33*

| Case | Flows | Risk level correct | Issues found (recall) | Alerts that were right (precision) | Contradiction correct | GDPR articles found |
| --- | --- | --- | --- | --- | --- | --- |
| **control_app** | 8 | 8/8 (100%) | 100% | 100% | 7/8 (88%) | 69% |
| **flo** | 11 | 11/11 (100%) | 100% | 100% | 9/11 (82%) | 100% |
| **trap_app** | 7 | 7/7 (100%) | 100% | 100% | 5/7 (71%) | 100% |
| **ALL** | 26 | 26/26 (100%) | 100% | 100% | 21/26 (81%) | 93% |

## Risk level: truth vs prediction (all cases)

| truth \ predicted | low | medium | high |
| --- | --- | --- | --- |
| **low** | 12 | 0 | 0 |
| **medium** | 0 | 7 | 0 |
| **high** | 0 | 0 | 7 |

## Errors to review

| Flow | Risk (truth → predicted) | Contradiction (truth → predicted) | Missing articles |
| --- | --- | --- | --- |
| CTL-02 | low → low | no → yes ❌ | — |
| CTL-05 | low → low | no → no | 5 |
| CTL-07 | low → low | no → no | 5, 17 |
| CTL-08 | low → low | no → no | 20 |
| FLO-08 | medium → medium | no → yes ❌ | — |
| FLO-10 | medium → medium | no → yes ❌ | — |
| TRP-01 | medium → medium | no → yes ❌ | — |
| TRP-03 | medium → medium | yes → no ❌ | — |

**How to read it.** *Recall*: share of real problems the tool found. *Precision*: share of the tool's alerts that were right. In compliance, recall matters most (a missed risk costs more than a false alert), but low precision makes the report unusable.