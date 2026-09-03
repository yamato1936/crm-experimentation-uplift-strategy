# CRM Experimentation & Uplift Targeting

Hillstrom Email Marketing Datasetを用いて、CRMキャンペーンの平均的な因果効果から、Treatment Effect Heterogeneity、Uplift Targeting、Policy Evaluation、次回RCTのPower Analysisまで一貫して評価した分析プロジェクトです。

> **CRMキャンペーンは本当にユーザー行動を改善したのか。全員に配信すべきか。それとも効果のあるユーザーだけに配信すべきか？**

単純なA/B Testで終わらせず、施策の因果効果を確認したうえで、targeting policyを本番導入できるだけの証拠があるかまで評価しています。

## 結論

### Men's Email

**Send Allを維持する。**

- Controlに対してVisit / Conversion / Spendすべてで正のITT効果
- 明確なTreatment Effect Heterogeneityの証拠は確認できず
- Uplift ranking performanceは弱い
- Top-k targetingはSend Allよりgross spendを低下させた

現時点では、Men's Emailをtargeting配信へ切り替える根拠は弱いと判断しました。

### Women's Email

**現時点ではSend Allを維持し、Top-10% targetingを次回RCTの検証候補とする。**

- Controlに対してVisit / Conversion / Spendすべてで正のITT効果
- Prior women's merchandise purchaseによるVisit / Conversionのheterogeneity signal
- Uplift modelでpositive ranking signal
- Top-10%では高いincremental spendが観測された
- ただしSend Allとのgross spend差は不確実
- Targeting policyはまだprospective validationされていない

したがって、**Targetingは有望だが、現在の証拠だけでSend Allを置き換えるべきではない**という判断です。

## 分析フロー

```text
Data Quality Audit
        |
Randomization Validation
        |
Experiment Population
        |
A/B Metrics
        |
Average Treatment Effect
        |
Treatment Effect Heterogeneity
        |
Uplift Modeling
        |
Policy Evaluation
        |
Prospective Experiment Design
        |
Power / Feasibility Analysis
```

## Dataset

総ユーザー数は64,000。Treatmentは3群です。

| Original Treatment | Analysis Label |
| --- | --- |
| No E-Mail | `control` |
| Mens E-Mail | `mens_email` |
| Womens E-Mail | `womens_email` |

主要Outcome:

- `visit`
- `conversion`
- `spend`

Pre-treatment covariates:

- `recency`
- `history`
- `history_segment`
- `mens`
- `womens`
- `zip_code`
- `newbie`
- `channel`

`visit`、`conversion`、`spend`はpost-treatment outcomeなので、Uplift Modelのfeatureには使用していません。

## 1. Randomization Validation

### Sample Ratio Mismatch

| Treatment | N |
| --- | ---: |
| Control | 21,306 |
| Men's Email | 21,307 |
| Women's Email | 21,387 |

```text
Chi-square = 0.203
p-value    = 0.904
SRM flag   = False
```

Pre-treatment covariatesの最大absolute SMDは約0.017で、`|SMD| >= 0.10`となる変数はありませんでした。

したがって、**SRMまたは重大なobserved pre-treatment imbalanceを示す証拠は確認されなかった**と判断しています。これはrandomizationが証明されたことを意味しません。

## 2. Average Treatment Effect

Intent-to-Treatとして、Men's Email / Women's EmailをControlと比較しました。6つのTreatment x Outcome comparisonにHolm correctionを適用しています。

### Men's Email vs Control

| Outcome | Control | Men's Email | ATE |
| --- | ---: | ---: | ---: |
| Visit Rate | 10.62% | 18.28% | **+7.66pp** |
| Conversion Rate | 0.57% | 1.25% | **+0.68pp** |
| Spend / User | 0.653 | 1.423 | **+0.770** |

### Women's Email vs Control

| Outcome | Control | Women's Email | ATE |
| --- | ---: | ---: | ---: |
| Visit Rate | 10.62% | 15.14% | **+4.52pp** |
| Conversion Rate | 0.57% | 0.88% | **+0.31pp** |
| Spend / User | 0.653 | 1.077 | **+0.424** |

6比較すべてHolm-adjusted significanceを満たしました。Spendはzero-inflatedかつheavy-tailedなため、Welch inferenceに加えてpercentile bootstrap CIも確認しています。

なお、Men's EmailとWomen's Emailを直接比較する検定は行っていないため、どちらが統計的に優れているかは主張していません。

## 3. Treatment Effect Heterogeneity

HC3 robust standard errorを用いたinteraction modelで、pre-treatment covariateによる効果の異質性を評価しました。

基本形:

```text
Y = beta0 + beta1*T + beta2*X + beta3*(T*X) + error
```

Women's Email x prior womens purchaseでは、Visit / Conversionにheterogeneity signalが確認されました。

```text
Visit interaction      = +6.20pp
95% CI                 = [4.95pp, 7.46pp]
Holm-adjusted p-value  < 0.001

Conversion interaction = +0.45pp
95% CI                  = [0.13pp, 0.77pp]
Holm-adjusted p-value   = 0.028
```

Spend interactionは有意ではなく、Men's Email x prior mens purchaseでも十分なinteraction evidenceは確認されませんでした。

これらのinteractionはdescriptive subgroup review後に選択したため、**confirmatoryではなくtargeted follow-up / exploratory analysis**として扱っています。

## 4. Uplift Modeling

T-Learnerを用い、以下を別々のbinary treatment problemとして学習しました。

```text
Men's Email vs Control
Women's Email vs Control
```

Predicted upliftは次の差として定義しています。

```text
predicted_uplift(x) = predicted_outcome_treatment(x)
                    - predicted_outcome_control(x)
```

Model featureはpre-treatment covariatesのみ。Training dataではなくheld-out sampleでQini、AUUC、Top-k upliftを評価しています。

| Treatment / Outcome | Qini |
| --- | ---: |
| Men's / Conversion | -0.00023 |
| Men's / Spend | +0.00430 |
| Women's / Conversion | +0.00067 |
| Women's / Spend | +0.03670 |

Women's Emailではranking signalが確認されましたが、predicted upliftはindividual causal effectそのものではなくmodel-based estimateです。

## 5. Policy Evaluation

Held-out predictionsを用いて以下のpolicyを比較しました。

- Send None
- Send All
- Top 10%
- Top 20%
- Top 30%
- Top 50%

Policy valueはInverse Propensity Weightingで推定しています。

```text
V(policy)
= E[
    policy(X) * T * Y / e
    + (1 - policy(X)) * (1 - T) * Y / (1 - e)
  ]
```

### Men's Email x Spend

| Policy | Policy Value | vs Send All |
| --- | ---: | ---: |
| Send All | 1.581 | 0.000 |
| Top 10% | 0.826 | -0.755 |
| Top 20% | 0.893 | -0.688 |
| Top 30% | 0.946 | -0.635 |
| Top 50% | 1.213 | -0.367 |

Men's EmailではTop-k policyがSend Allよりgross spendを低下させました。

### Women's Email x Spend

| Policy | Policy Value | vs Send All |
| --- | ---: | ---: |
| Send All | 1.156 | 0.000 |
| Top 10% | 0.855 | -0.301 |
| Top 20% | 0.838 | -0.317 |
| Top 30% | 0.868 | -0.287 |
| Top 50% | 0.895 | -0.261 |

Top-10% vs Send All:

```text
Difference = -0.301
95% CI     = [-0.745, +0.114]
```

CIは0を跨いでいるため、Top-10% targetingがSend Allと同等以上のgross spendを維持するとは結論できません。一方で、lossの大きさ自体にも不確実性があります。

## 6. Break-even Delivery Cost

Hillstrom Datasetには実際のdelivery costやgross marginがありません。そのため架空の利益率を置かず、Spendと同じ単位でrevenue-equivalent break-even costを計算しました。

```text
net_value(policy, cost)
= policy_value - cost * treatment_rate
```

Women's Email Top-10%のSend Allに対するpoint-estimate break-even costは約0.334 / emailです。

ただし、これはprofit thresholdではありません。実務では次のようにgross marginを含めて判断する必要があります。

```text
Net Value = Gross Margin * Incremental Spend - Delivery Cost
```

## 7. Prospective Experiment Design

Women's Top-10% targetingはそのままproductionへ導入せず、次回RCTで検証します。

- **Arm A:** Send All
- **Arm B:** Frozen Top-10% Uplift Policy

Experiment開始前にfeature set、model、hyperparameters、scoring logic、target fraction、thresholdをfreezeします。

Primary estimand:

```text
Delta = E[Spend | Targeting] - E[Spend | Send All]
```

配信量を約90%削減するpolicyであるため、superiorityだけでなくnon-inferiority designを主要候補とします。

```text
H0: Delta <= -Margin
H1: Delta >  -Margin
```

Marginは必要sample sizeを小さくするために選ばず、gross margin、delivery cost、business toleranceから事前に決定します。

## 8. Power Analysis

Historical planning SDは16.76です。

### Two-sided MDE sensitivity

| Spend/User MDE | Required Total N |
| ---: | ---: |
| 0.10 | 881,424 |
| 0.20 | 220,356 |
| 0.30 | 97,936 |
| 0.40 | 55,090 |
| 0.50 | 35,258 |

### Non-inferiority sensitivity: true difference = 0

| NI Margin | Required Total N |
| ---: | ---: |
| 0.10 | 694,298 |
| 0.20 | 173,576 |
| 0.30 | 77,146 |
| 0.40 | 43,394 |
| 0.50 | 27,772 |

Historical point estimate `Delta = -0.300664` をplanning truthとして仮定すると、Margin 0.10 / 0.20 / 0.30ではnon-inferiority達成不可、Margin 0.40では約703,610 users、Margin 0.50では約174,734 usersが必要です。

## Tech Stack

- BigQuery / GoogleSQL
- Python
- pandas / NumPy / SciPy
- statsmodels
- scikit-learn
- pytest

## Repository Structure

```text
.
├── README.md
├── data
│   ├── processed
│   └── raw
├── docs
│   ├── decision_memo.md
│   ├── experiment_design.md
│   └── methodology.md
├── figures
├── sql
│   ├── 00_data_audit.sql
│   ├── 01_experiment_population.sql
│   ├── 02_ab_metrics.sql
│   └── 03_segment_analysis.sql
├── src
│   ├── estimate_ate.py
│   ├── heterogeneity.py
│   ├── policy_evaluation.py
│   ├── power_analysis.py
│   ├── uplift_model.py
│   └── validate_randomization.py
└── tests
    ├── test_metrics.py
    └── test_randomization.py
```

## Reproduce

```bash
python src/validate_randomization.py \
  --project hillstrom-experiment-20260828 \
  --table ceus.hillstrom_raw

python src/estimate_ate.py \
  --project hillstrom-experiment-20260828 \
  --table ceus.experiment_population

python src/uplift_model.py \
  --project hillstrom-experiment-20260828 \
  --table ceus.experiment_population

python src/policy_evaluation.py
python src/power_analysis.py
pytest -q
```

Current regression-test status:

```text
20 passed
```

## Documentation

- [Decision Memo](docs/decision_memo.md) - 分析結果から何を意思決定するか
- [Methodology](docs/methodology.md) - どの統計手法・設計思想で分析したか
- [Experiment Design](docs/experiment_design.md) - Women's Top-10% targetingを次回RCTでどう検証するか

## Analytical Guardrails

- SRM / covariate balanceだけで「randomization成功」と断定しない
- Men's EmailとWomen's Emailを直接比較していないため、どちらが統計的に優れているか断定しない
- Post-treatment variableでsegmentを作らない
- Conversionしたユーザーだけに限定してSpendを比較しない
- Descriptive subgroup review後のinteractionをconfirmatoryと呼ばない
- Predicted upliftをindividual causal effectそのものと解釈しない
- Training dataでuplift policyを評価しない
- Held-outで最良だったTop-kを即production policyにしない
- SpendをProfitと呼ばない
- Sample sizeを小さくするためにnon-inferiority marginを変更しない

## Final Takeaway

このプロジェクトでは、A/B Testの有意差確認で終了せず、因果推論、heterogeneity、causal ML、policy evaluation、prospective experiment designまで接続しました。

**Men's EmailはSend Allを維持。Women's Emailも現時点ではSend Allを維持し、Top-10% targetingはprospective validation対象とする。**
