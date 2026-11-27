# Corrections 2026-10-22: Anchors selected inside the training partition (code/anchor_trainsel.py)

Fit half: GBM training and anchor candidates. Selection half: selection by host F1. Both halves are
training hosts. Held-out F1: all held-out hosts (the test partition of the main tables), read only after
the queries are frozen. Test-half F1: the test half of anchor_frozen.py, for comparison. PSI-Miner row:
rules mined on all training hosts, rule selected on the selection half (overlaps the mining hosts).

## Delay sweep (results_xai_v2)

Counts per run: fit / selection (training partition) / held-out / test half, hosts (anomalous).

| config | L | method | selection F1 | held-out F1 | test-half F1 | planted | runs | query (first run) |
|---|---|---|---|---|---|---|---|---|
| gap1-2 | L3 | anchors_modal (fit half only) | 0.936 +- 0.033 | 0.941 +- 0.006 | 0.931 +- 0.014 | 3/3 | 3 | DPORT_MANY_lag0 && SYN_DOM_lag1 |
| gap1-2 | L3 | anchors_selsel (selection-half F1) | 0.947 +- 0.015 | 0.937 +- 0.013 | 0.931 +- 0.014 | 3/3 | 3 | DPORT_MANY_lag0 && SYN_DOM_lag2 |
| gap1-2 | L3 | gbm fit half (model) | 1.000 +- 0.000 | 1.000 +- 0.000 | 1.000 +- 0.000 | 0/3 | 3 | gradient boosting, 52 features |
| gap1-2 | L3 | psiminer_selsel (mined on all training hosts) | - | 1.000 +- 0.000 | 1.000 +- 0.000 | 3/3 | 3 | SYN_DOM ##[ 0.000000 : 2.000000 ] !SYN_DOM ##[ 0.000000 : 1.000000 ] DPORT_MANY |
| gap1-2 | L8 | anchors_modal (fit half only) | 0.936 +- 0.033 | 0.941 +- 0.006 | 0.931 +- 0.014 | 3/3 | 3 | DPORT_MANY_lag0 && SYN_DOM_lag1 |
| gap1-2 | L8 | anchors_selsel (selection-half F1) | 0.947 +- 0.015 | 0.937 +- 0.013 | 0.931 +- 0.014 | 3/3 | 3 | DPORT_MANY_lag0 && SYN_DOM_lag2 |
| gap1-2 | L8 | gbm fit half (model) | 1.000 +- 0.000 | 1.000 +- 0.000 | 1.000 +- 0.000 | 0/3 | 3 | gradient boosting, 117 features |
| gap1-2 | L8 | psiminer_selsel (mined on all training hosts) | - | 1.000 +- 0.000 | 1.000 +- 0.000 | 3/3 | 3 | SYN_DOM ##[ 0.000000 : 2.000000 ] !SYN_DOM ##[ 0.000000 : 1.000000 ] DPORT_MANY |
| gap1-4 | L3 | anchors_modal (fit half only) | 0.747 +- 0.022 | 0.770 +- 0.011 | 0.757 +- 0.017 | 3/3 | 3 | DPORT_MANY_lag0 && SYN_DOM_lag2 |
| gap1-4 | L3 | anchors_selsel (selection-half F1) | 0.767 +- 0.015 | 0.763 +- 0.009 | 0.746 +- 0.013 | 3/3 | 3 | DPORT_MANY_lag0 && SYN_DOM_lag1 |
| gap1-4 | L3 | gbm fit half (model) | 0.989 +- 0.008 | 0.994 +- 0.002 | 0.998 +- 0.004 | 0/3 | 3 | gradient boosting, 52 features |
| gap1-4 | L3 | psiminer_selsel (mined on all training hosts) | - | 1.000 +- 0.000 | 1.000 +- 0.000 | 3/3 | 3 | SYN_DOM ##[ 0.000000 : 3.000000 ] !SYN_DOM ##[ 0.000000 : 2.000000 ] !SYN_DOM ## |
| gap1-4 | L8 | anchors_modal (fit half only) | 0.732 +- 0.047 | 0.748 +- 0.031 | 0.738 +- 0.023 | 3/3 | 3 | DPORT_MANY_lag0 && SYN_DOM_lag4 |
| gap1-4 | L8 | anchors_selsel (selection-half F1) | 0.767 +- 0.015 | 0.763 +- 0.009 | 0.746 +- 0.013 | 3/3 | 3 | DPORT_MANY_lag0 && SYN_DOM_lag1 |
| gap1-4 | L8 | gbm fit half (model) | 1.000 +- 0.000 | 1.000 +- 0.000 | 1.000 +- 0.000 | 0/3 | 3 | gradient boosting, 117 features |
| gap1-4 | L8 | psiminer_selsel (mined on all training hosts) | - | 1.000 +- 0.000 | 1.000 +- 0.000 | 3/3 | 3 | SYN_DOM ##[ 0.000000 : 3.000000 ] !SYN_DOM ##[ 0.000000 : 2.000000 ] !SYN_DOM ## |
| gap1-6 | L3 | anchors_modal (fit half only) | 0.600 +- 0.042 | 0.546 +- 0.045 | 0.569 +- 0.078 | 0/3 | 3 | DPORT_MANY_lag0 && SYN_DOM_lag3 |
| gap1-6 | L3 | anchors_selsel (selection-half F1) | 0.658 +- 0.037 | 0.588 +- 0.053 | 0.578 +- 0.087 | 0/3 | 3 | DPORT_MANY_lag0 && SYN_DOM_lag3 |
| gap1-6 | L3 | gbm fit half (model) | 0.903 +- 0.041 | 0.879 +- 0.050 | 0.883 +- 0.042 | 0/3 | 3 | gradient boosting, 52 features |
| gap1-6 | L3 | psiminer_selsel (mined on all training hosts) | - | 1.000 +- 0.000 | 1.000 +- 0.000 | 3/3 | 3 | SYN_DOM ##[ 0.000000 : 3.000000 ] !SYN_DOM ##[ 0.000000 : 2.000000 ] !SYN_DOM ## |
| gap1-6 | L8 | anchors_modal (fit half only) | 0.600 +- 0.042 | 0.556 +- 0.054 | 0.550 +- 0.068 | 0/3 | 3 | DPORT_MANY_lag0 && SYN_DOM_lag6 |
| gap1-6 | L8 | anchors_selsel (selection-half F1) | 0.666 +- 0.023 | 0.581 +- 0.058 | 0.568 +- 0.083 | 0/3 | 3 | DPORT_MANY_lag0 && SYN_DOM_lag4 |
| gap1-6 | L8 | gbm fit half (model) | 1.000 +- 0.000 | 1.000 +- 0.000 | 1.000 +- 0.000 | 0/3 | 3 | gradient boosting, 117 features |
| gap1-6 | L8 | psiminer_selsel (mined on all training hosts) | - | 1.000 +- 0.000 | 1.000 +- 0.000 | 3/3 | 3 | SYN_DOM ##[ 0.000000 : 3.000000 ] !SYN_DOM ##[ 0.000000 : 2.000000 ] !SYN_DOM ## |
| gap1-8 | L3 | anchors_modal (fit half only) | 0.684 +- 0.044 | 0.637 +- 0.050 | 0.595 +- 0.097 | 0/3 | 3 | DPORT_MANY_lag0 && !SMALL_DOM_lag1 |
| gap1-8 | L3 | anchors_selsel (selection-half F1) | 0.716 +- 0.031 | 0.660 +- 0.025 | 0.613 +- 0.072 | 0/3 | 3 | ACTIVE_lag3 && DPORT_MANY_lag0 && !SMALL_DOM_lag1 |
| gap1-8 | L3 | gbm fit half (model) | 0.752 +- 0.043 | 0.716 +- 0.046 | 0.690 +- 0.033 | 0/3 | 3 | gradient boosting, 52 features |
| gap1-8 | L3 | psiminer_selsel (mined on all training hosts) | - | 0.993 +- 0.007 | 0.990 +- 0.008 | 3/3 | 3 | SYN_DOM ##[ 0.000000 : 3.000000 ] !SYN_DOM ##[ 0.000000 : 2.000000 ] !SYN_DOM ## |
| gap1-8 | L8 | anchors_modal (fit half only) | 0.498 +- 0.119 | 0.471 +- 0.036 | 0.444 +- 0.017 | 0/3 | 3 | DPORT_MANY_lag0 && SYN_DOM_lag4 |
| gap1-8 | L8 | anchors_selsel (selection-half F1) | 0.592 +- 0.034 | 0.515 +- 0.079 | 0.514 +- 0.071 | 0/3 | 3 | DPORT_MANY_lag0 && SYN_DOM_lag6 |
| gap1-8 | L8 | gbm fit half (model) | 1.000 +- 0.000 | 1.000 +- 0.000 | 1.000 +- 0.000 | 0/3 | 3 | gradient boosting, 117 features |
| gap1-8 | L8 | psiminer_selsel (mined on all training hosts) | - | 0.993 +- 0.007 | 0.990 +- 0.008 | 3/3 | 3 | SYN_DOM ##[ 0.000000 : 3.000000 ] !SYN_DOM ##[ 0.000000 : 2.000000 ] !SYN_DOM ## |

Host counts seen: 142 (74) / 147 (76) / 307 (146) / 149 (70)

## Stray events (results_xai)

Counts per run: fit / selection (training partition) / held-out / test half, hosts (anomalous).

| config | L | method | selection F1 | held-out F1 | test-half F1 | planted | runs | query (first run) |
|---|---|---|---|---|---|---|---|---|
| noise0 | L3 | anchors_modal (fit half only) | 1.000 +- 0.000 | 1.000 +- 0.000 | 1.000 +- 0.000 | 3/3 | 3 | DPORT_MANY_lag0 && SYN_DOM_lag2 |
| noise0 | L3 | anchors_selsel (selection-half F1) | 1.000 +- 0.000 | 1.000 +- 0.000 | 1.000 +- 0.000 | 3/3 | 3 | DPORT_MANY_lag0 && SYN_DOM_lag2 |
| noise0 | L3 | gbm fit half (model) | 1.000 +- 0.000 | 1.000 +- 0.000 | 1.000 +- 0.000 | 0/3 | 3 | gradient boosting, 52 features |
| noise0 | L3 | psiminer_selsel (mined on all training hosts) | - | 1.000 +- 0.000 | 1.000 +- 0.000 | 3/3 | 3 | SYN_DOM ##[ 1.000000 : 2.000000 ] DPORT_MANY |
| noise0.01 | L3 | anchors_modal (fit half only) | 0.994 +- 0.000 | 0.982 +- 0.002 | 0.977 +- 0.004 | 3/3 | 3 | DPORT_MANY_lag0 && SYN_DOM_lag2 |
| noise0.01 | L3 | anchors_selsel (selection-half F1) | 0.994 +- 0.000 | 0.982 +- 0.002 | 0.977 +- 0.004 | 3/3 | 3 | DPORT_MANY_lag0 && SYN_DOM_lag2 |
| noise0.01 | L3 | gbm fit half (model) | 0.994 +- 0.000 | 0.982 +- 0.002 | 0.977 +- 0.004 | 0/3 | 3 | gradient boosting, 52 features |
| noise0.01 | L3 | psiminer_selsel (mined on all training hosts) | - | 0.645 +- 0.000 | 0.639 +- 0.000 | 0/3 | 3 | !DPORT_MANY && !SYN_DOM && !SMALL_DOM ##[ 0.000000 : 1.000000 ] !DPORT_MANY |
| noise0.02 | L3 | anchors_modal (fit half only) | 0.987 +- 0.006 | 0.966 +- 0.014 | 0.966 +- 0.012 | 3/3 | 3 | DPORT_MANY_lag0 && SYN_DOM_lag2 |
| noise0.02 | L3 | anchors_selsel (selection-half F1) | 0.987 +- 0.006 | 0.966 +- 0.014 | 0.966 +- 0.012 | 3/3 | 3 | DPORT_MANY_lag0 && SYN_DOM_lag2 |
| noise0.02 | L3 | gbm fit half (model) | 0.987 +- 0.006 | 0.968 +- 0.011 | 0.968 +- 0.010 | 0/3 | 3 | gradient boosting, 52 features |
| noise0.02 | L3 | psiminer_selsel (mined on all training hosts) | - | 0.645 +- 0.000 | 0.639 +- 0.000 | 0/3 | 3 | !DPORT_MANY && !SYN_DOM && !SMALL_DOM ##[ 0.000000 : 1.000000 ] !DPORT_MANY |
| noise0.05 | L3 | anchors_modal (fit half only) | 0.933 +- 0.017 | 0.912 +- 0.018 | 0.911 +- 0.019 | 3/3 | 3 | DPORT_MANY_lag0 && SYN_DOM_lag2 |
| noise0.05 | L3 | anchors_selsel (selection-half F1) | 0.933 +- 0.017 | 0.912 +- 0.018 | 0.911 +- 0.019 | 3/3 | 3 | DPORT_MANY_lag0 && SYN_DOM_lag2 |
| noise0.05 | L3 | gbm fit half (model) | 0.933 +- 0.017 | 0.913 +- 0.018 | 0.913 +- 0.017 | 0/3 | 3 | gradient boosting, 52 features |
| noise0.05 | L3 | psiminer_selsel (mined on all training hosts) | - | 0.645 +- 0.000 | 0.639 +- 0.000 | 0/3 | 3 | !DPORT_MANY && !SYN_DOM && !SMALL_DOM ##[ 0.000000 : 1.000000 ] !DPORT_MANY |
| noise0.1 | L3 | anchors_modal (fit half only) | 0.871 +- 0.021 | 0.848 +- 0.021 | 0.854 +- 0.027 | 3/3 | 3 | DPORT_MANY_lag0 && SYN_DOM_lag2 |
| noise0.1 | L3 | anchors_selsel (selection-half F1) | 0.876 +- 0.020 | 0.849 +- 0.022 | 0.854 +- 0.027 | 3/3 | 3 | DPORT_MANY_lag0 && SYN_DOM_lag2 |
| noise0.1 | L3 | gbm fit half (model) | 0.871 +- 0.021 | 0.849 +- 0.021 | 0.854 +- 0.027 | 0/3 | 3 | gradient boosting, 52 features |
| noise0.1 | L3 | psiminer_selsel (mined on all training hosts) | - | 0.645 +- 0.000 | 0.639 +- 0.000 | 0/3 | 3 | !DPORT_MANY && !SYN_DOM && !SMALL_DOM ##[ 0.000000 : 1.000000 ] !DPORT_MANY |

Host counts seen: 142 (74) / 147 (76) / 307 (146) / 149 (70)

## MAWI five splits (results_dc)

Counts per run: fit / selection (training partition) / held-out / test half, hosts (anomalous).

| config | L | method | selection F1 | held-out F1 | test-half F1 | planted | runs | query (first run) |
|---|---|---|---|---|---|---|---|---|
| dc | L3 | anchors_modal (fit half only) | 0.417 +- 0.209 | 0.333 +- 0.144 | 0.339 +- 0.147 | - | 5 | ACTIVE_lag0 && !ACTIVE_lag2 && !BPP_LARGE_lag0 && !ICMP_lag0 && !SYN_DOM_lag0 && |
| dc | L3 | anchors_selsel (selection-half F1) | 0.504 +- 0.158 | 0.468 +- 0.040 | 0.477 +- 0.035 | - | 5 | ACTIVE_lag0 && !ACTIVE_lag2 && !ACTIVE_lag3 && PKTS_HI_lag0 && SMALL_DOM_lag0 && |
| dc | L3 | gbm fit half (model) | 0.595 +- 0.071 | 0.468 +- 0.017 | 0.474 +- 0.012 | - | 5 | gradient boosting, 52 features |

Host counts seen: 148 (80) / 152 (70) / 13712 (3427) / 6822 (1704); 148 (80) / 152 (70) / 13918 (3483) / 6970 (1778); 152 (79) / 148 (71) / 13877 (3503) / 6965 (1745); 153 (78) / 147 (72) / 13725 (3512) / 6908 (1773); 156 (79) / 144 (71) / 13974 (3480) / 6917 (1741)

