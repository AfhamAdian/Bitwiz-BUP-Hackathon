# Generated valid edge cases

| ID | Purpose | Optimal cost (BDT) | Hand checked |
|---|---|---:|---|
| EDGE-001 | Zero demand and solar; zero-capacity battery | 0 | yes |
| EDGE-002 | Pure grid, no storage | 144 | yes |
| EDGE-003 | Excess solar must be curtailed, no export | 0 | yes |
| EDGE-004 | Solar exactly meets demand | 0 | yes |
| EDGE-005 | Free grid tariff and many equivalent optima | 0 | yes |
| EDGE-006 | Flat tariff; peak is not an optimization objective | 144 | yes |
| EDGE-007 | Capacity equals base reserve; battery locked | 48 | yes |
| EDGE-008 | Zero charge rate prevents net discharge over day | 48 | yes |
| EDGE-009 | Zero discharge rate prevents net charge over day | 48 | yes |
| EDGE-010 | Grid charging for later demand | 10 | yes |
| EDGE-011 | Initial battery may be used if replenished later | 5 | yes |
| EDGE-012 | Cannot use future cheap energy to supply hour-zero load | 50 | yes |
| EDGE-013 | Charge rate binds before an expensive hour | 32 | yes |
| EDGE-014 | Discharge rate binds | 32 | yes |
| EDGE-015 | Capacity binds | 32 | yes |
| EDGE-016 | Store surplus solar for evening | 0 | yes |
| EDGE-017 | Solar fraction remaining 0 | 20 | yes |
| EDGE-018 | Solar fraction remaining 1 | 0 | yes |
| EDGE-019 | Solar fraction remaining 0.2 | 16 | yes |
| EDGE-020 | Solar fraction remaining 0.8 | 4 | yes |
| EDGE-021 | Solar reduction when forecast is zero | 1 | yes |
| EDGE-022 | Reserve enforced after first hour, not before | 5 | yes |
| EDGE-023 | Reserve below base does not weaken base reserve | 24 | yes |
| EDGE-024 | 100 percent capacity reserve | 6 | yes |
| EDGE-025 | Final-hour reserve equals initial energy | 24 | yes |
| EDGE-026 | No charge blocks cheapest hour | 50 | yes |
| EDGE-027 | No discharge blocks expensive hour | 50 | yes |
| EDGE-028 | Both action windows overlap: idle is feasible | 24 | yes |
| EDGE-029 | Grid cap forces expensive precharging | 50 | yes |
| EDGE-030 | Hour-zero grid outage uses initial energy | 5 | yes |
| EDGE-031 | All-day zero grid cap with sufficient solar | 0 | yes |
| EDGE-032 | Repeated overlapping reserves use strongest bound | 24 | yes |
| EDGE-033 | Overlapping grid caps use tightest bound | 48 | yes |
| EDGE-034 | Fractional inputs without premature rounding | 2.0625 | yes |
| EDGE-035 | Unsorted request hours are still complete and unique | 24 | yes |
| EDGE-036 | Three irrelevant notes preserve order | 24 | yes |
| EDGE-037 | Three relevant directives applied together | 25 | yes |
| EDGE-038 | Equivalent solar paraphrase | 25.6 | yes |
| EDGE-039 | Equivalent solar paraphrase | 25.6 | yes |
| EDGE-040 | Equivalent solar paraphrase | 25.6 | yes |
| EDGE-041 | All-day no-charge window | 24 | yes |
| EDGE-042 | All-day no-discharge window | 24 | yes |
| EDGE-043 | Large finite values; no published maximum | 2.4e+11 | yes |
