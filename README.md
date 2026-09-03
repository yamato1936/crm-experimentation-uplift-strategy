# CRM Experimentation & Uplift Targeting

Hillstrom Email Marketing Datasetを用いて、CRMキャンペーンの**平均的な因果効果、Treatment Effect Heterogeneity、Uplift Targeting、Policy Value、次回実験の必要sample size**まで一貫して評価したプロジェクトです。

単純なA/B Testで終わらせず、

> **CRMキャンペーンは本当にユーザー行動を改善したのか。全員に配信すべきか。それとも効果のあるユーザーだけに配信すべきか？**

という意思決定まで分析を接続しています。

---

## 結論

### Men's Email

**Send Allを維持する。**

* Controlに対してVisit / Conversion / Spendすべてで正のITT効果
* 明確なTreatment Effect Heterogeneityの証拠は確認できず
* Uplift ranking performanceも弱い
* Top-k targetingはSend Allよりgross spendを低下させた

現時点では、Men's Emailをtargeting配信へ切り替える根拠は弱いと判断しました。

### Women's Email

**現時点ではSend Allを維持し、Top-10% targetingを次回RCTの検証候補とする。**

* Controlに対してVisit / Conversion / Spendすべてで正のITT効果
* Prior women's merchandise purchaseによるVisit / Conversionのheterogeneity signal
* Uplift modelでpositive ranking signal
* Top-10%では高いincremental spendが観測された
* ただしSend Allとのgross spend差は不確実
* Targeting policyはまだprospective validationされていない

したがって、

> **Targetingは有望だが、現在の証拠だけでSend Allを置き換えるべきではない**

という意思決定になりました。

---

# Analysis Flow

```text
Data Quality Audit
        ↓
Randomization Validation
        ↓
Experiment Population
        ↓
A/B Metrics
        ↓
Average Treatment Effect
        ↓
Treatment Effect Heterogeneity
        ↓
Uplift Modeling
        ↓
Policy Evaluation
        ↓
Prospective Experiment Design
        ↓
Power / Feasibility Analysis
```

分析の目的はモデルを作ることではなく、

> **因果効果を確認し、誰に施策を打つべきかを推定し、そのpolicyを本番導入できるだけの証拠があるか判断すること**

です。

---

# Dataset

Hillstrom Email Marketing Datasetを使用しています。

総ユーザー数：

```text
64,000
```

Treatmentは3群です。

| Original Treatment | Analysis Label |
| ------------------ | -------------- |
| No E-Mail          | `control`      |
| Mens E-Mail        | `mens_email`   |
| Womens E-Mail      | `womens_email` |

主要Outcome：

* `visit`
* `conversion`
* `spend`

Pre-treatment covariates：

* `recency`
* `history`
* `history_segment`
* `mens`
* `womens`
* `zip_code`
* `newbie`
* `channel`

`visit`、`conversion`、`spend`はpost-treatment outcomeなので、Uplift Modelのfeatureには使用していません。

---

# 1. Data Quality Audit

BigQuery / GoogleSQLで分析前のdata auditを実施しました。

主な確認項目：

* Row count
* Missingness
* Treatment domain
* Binary variable domain
* Numeric range
* Outcome consistency
* Duplicate-like row patterns

結果：

* Total rows: **64,000**
* Missing values: **0**
* Invalid binary values: **0**
* Outcome logical inconsistencies: **0**

明示的なcustomer IDは存在しません。

そのため、全observed columnsが一致する行が存在しても、

> 同一人物のduplicateとは判断せず削除しない

という方針を採用しています。

---

# 2. Randomization Validation

A/B Testの結果を見る前に、randomizationに重大な異常がないか確認しました。

## Sample Ratio Mismatch

Treatment counts：

| Treatment     |      N |
| ------------- | -----: |
| Control       | 21,306 |
| Men's Email   | 21,307 |
| Women's Email | 21,387 |

SRM test：

```text
Chi-square = 0.203
p-value    = 0.904
```

Sample Ratio Mismatchを示す証拠は確認されませんでした。

## Pre-treatment Balance

Standardized Mean Differenceを用いてTreatment間のcovariate balanceを確認しました。

最大absolute SMD：

```text
≈ 0.017
```

`|SMD| >= 0.10`となるcovariateはありませんでした。

したがって、

> **SRMまたは重大なobserved pre-treatment imbalanceを示す証拠は確認されなかった**

と判断しています。

「randomizationが証明された」とは表現していません。

---

# 3. Average Treatment Effect

Intent-to-Treatとして、

* Men's Email vs Control
* Women's Email vs Control

を、

* Visit
* Conversion
* Spend

について評価しました。

合計6つのTreatment × Outcome comparisonに対してHolm correctionを適用しています。

## Men's Email vs Control

| Outcome         | Control | Men's Email |         ATE |
| --------------- | ------: | ----------: | ----------: |
| Visit Rate      |  10.62% |      18.28% | **+7.66pp** |
| Conversion Rate |   0.57% |       1.25% | **+0.68pp** |
| Spend / User    |   0.653 |       1.423 |  **+0.770** |

すべてHolm-adjusted significanceを満たしました。

## Women's Email vs Control

| Outcome         | Control | Women's Email |         ATE |
| --------------- | ------: | ------------: | ----------: |
| Visit Rate      |  10.62% |        15.14% | **+4.52pp** |
| Conversion Rate |   0.57% |         0.88% | **+0.31pp** |
| Spend / User    |   0.653 |         1.077 |  **+0.424** |

こちらもすべてHolm-adjusted significanceを満たしました。

Spendはzero-inflatedかつheavy-tailedなため、

* Welch confidence interval
* Percentile bootstrap confidence interval

の両方を確認しています。

---

# 4. Treatment Effect Heterogeneity

平均効果だけでなく、

> **誰により強く効いているか**

をinteraction modelで検証しました。

モデルの基本形：

$$
Y_i
=
\beta_0
+
\beta_1T_i
+
\beta_2X_i
+
\beta_3(T_iX_i)
+
\epsilon_i
$$

HC3 robust standard errorを使用しています。

## Women's Email × prior womens purchase

### Visit

Interaction：

```text
+6.20pp
95% CI: [4.95pp, 7.46pp]
Holm-adjusted p < 0.001
```

Stratum-specific effect：

```text
womens = 0 → +1.11pp
womens = 1 → +7.31pp
```

### Conversion

Interaction：

```text
+0.45pp
95% CI: [0.13pp, 0.77pp]
Holm-adjusted p = 0.028
```

Stratum-specific effect：

```text
womens = 0 → +0.06pp
womens = 1 → +0.51pp
```

Spendについては十分なinteraction evidenceを確認できませんでした。

## Men's Email × prior mens purchase

Visit / Conversion / Spendのいずれでも十分なheterogeneity evidenceは確認できませんでした。

なお、このinteraction hypothesisはdescriptive subgroup review後に選択しています。

そのため、

> **confirmatory analysisではなくtargeted follow-up analysis**

として扱い、post-selection limitationを明記しています。

---

# 5. Uplift Modeling

平均Treatment Effectではなく、

$$
\tau(x)
=
E[Y(1)-Y(0)\mid X=x]
$$

をrankingするため、T-Learnerを構築しました。

3-armを無理に1つのbinary problemへ変換せず、

```text
Men's Email vs Control
Women's Email vs Control
```

を別々に学習しています。

Model：

```text
T-Learner
└── Random Forest
```

Model featureはpre-treatment covariatesのみです。

Training dataでpolicyを評価せず、held-out sampleで、

* Qini
* AUUC
* Uplift@10%
* Uplift@20%
* Uplift@30%
* Uplift@50%

を評価しています。

---

## Men's Email

### Conversion

```text
Qini = -0.00023
```

### Spend

```text
Qini = +0.00430
```

Targetingによる明確なuplift concentrationは確認できませんでした。

---

## Women's Email

### Conversion

```text
Qini = +0.00067
```

Top 20%：

```text
Observed uplift = +1.05pp
95% CI = [0.23pp, 1.88pp]
```

### Spend

```text
Qini = +0.03670
```

Top 10%：

```text
Observed uplift = +2.486 / user
95% CI = [0.428, 4.544]
```

Women's Emailでは、Men's Emailより明確なuplift ranking signalが観測されました。

ただし、Individual Treatment Effectそのものを観測しているわけではないため、

> predicted upliftはindividual-level causal truthではなくmodel-based estimate

として扱っています。

---

# 6. Policy Evaluation

Uplift modelを「予測モデル」として終わらせず、実際の配信policyとして評価しました。

比較Policy：

```text
Send None
Send All
Top 10%
Top 20%
Top 30%
Top 50%
```

Policy valueはheld-out observations上でInverse Propensity Weightingにより推定しています。

$$
V(\pi)
=
E
\left[
\pi(X)\frac{TY}{e}
+
(1-\pi(X))
\frac{(1-T)Y}{1-e}
\right]
$$

---

## Men's Email × Spend

| Policy   | Policy Value | vs Send All |
| -------- | -----------: | ----------: |
| Send All |        1.581 |       0.000 |
| Top 10%  |        0.826 |      -0.755 |
| Top 20%  |        0.893 |      -0.688 |
| Top 30%  |        0.946 |      -0.635 |
| Top 50%  |        1.213 |      -0.367 |

すべてのTop-k policyでSend Allよりgross spendが低く、95% CIも0を跨ぎませんでした。

**Men's EmailはSend Allを維持する**という判断を支持しています。

---

## Women's Email × Spend

| Policy   | Policy Value | vs Send All |
| -------- | -----------: | ----------: |
| Send All |        1.156 |       0.000 |
| Top 10%  |        0.855 |      -0.301 |
| Top 20%  |        0.838 |      -0.317 |
| Top 30%  |        0.868 |      -0.287 |
| Top 50%  |        0.895 |      -0.261 |

Top-10% vs Send All：

```text
Difference = -0.301
95% CI     = [-0.745, +0.114]
```

したがって、

> Top-10% targetingがSend Allと同等以上のgross spendを維持する

とはまだ結論できません。

一方でCIは0を跨いでおり、gross spend lossの大きさも不確実です。

---

# 7. Break-even Delivery Cost

Hillstrom Datasetには実際のEmail delivery costやgross marginがありません。

そこで架空のコストを設定せず、

> **どのdelivery costならtargetingがSend Allより有利になるか**

を逆算しました。

Policy \(\pi\) の配信率を \(r_\pi\)、1配信あたりcostを \(c\) とすると、

$$
NetValue(\pi,c)
=
V(\pi)-cr_\pi
$$

Send Allとのbreak-even pointは、

$$
c^*
=
\frac{V(All)-V(\pi)}
{1-r_\pi}
$$

となります。

Women's Email Top-10%：

```text
Revenue-equivalent break-even cost ≈ 0.334 / email
```

ただし、これはprofit thresholdではありません。

実務では、

$$
NetValue
=
GrossMargin
\times
IncrementalSpend
-
DeliveryCost
$$

で判断する必要があります。

---

# 8. Prospective Experiment Design

Women's Email Top-10% targetingをそのまま本番導入せず、次回RCTで検証する設計まで行いました。

## Arm A

```text
Send All
```

eligible user全員にWomen's Emailを送信。

## Arm B

```text
Frozen Top-10% Uplift Policy
```

事前に固定したuplift modelで上位10%のユーザーだけにWomen's Emailを送信。

Experiment開始前に以下をfreezeします。

* Feature set
* Model
* Hyperparameters
* Scoring logic
* Model version
* Targeting fraction
* Threshold
* Tie handling

Outcomeを確認してからmodelやthresholdを変更しません。

---

# 9. Non-inferiority Design

Targetingは配信量を約90%削減するため、単純なsuperiority testではなくnon-inferiority designを主要候補としました。

Primary estimand：

$$
\Delta
=
E[Spend\mid Targeting]
-
E[Spend\mid SendAll]
$$

Hypothesis：

$$
H_0:
\Delta\le-M
$$

$$
H_1:
\Delta>-M
$$

ここで \(M\) は事業上許容できるSpend/User lossです。

Marginは必要sample sizeを小さくするために選ばず、

* Gross margin
* Delivery cost
* Opportunity cost
* Business tolerance

から事前に決定する必要があります。

---

# 10. Power Analysis

Spendは非常に高分散でした。

Historical planning SD：

```text
Women's Email SD = 16.76
Control SD       = 10.25

Planning SD      = 16.76
```

保守的に大きい方を使用しています。

## Two-sided MDE Sensitivity

| Spend/User MDE | Required Total N |
| -------------: | ---------------: |
|           0.10 |          881,424 |
|           0.20 |          220,356 |
|           0.30 |           97,936 |
|           0.40 |           55,090 |
|           0.50 |           35,258 |

## Non-inferiority

真のpolicy differenceを0と仮定した場合：

| NI Margin | Required Total N |
| --------: | ---------------: |
|      0.10 |          694,298 |
|      0.20 |          173,576 |
|      0.30 |           77,146 |
|      0.40 |           43,394 |
|      0.50 |           27,772 |

一方、今回観測した、

$$
\Delta=-0.300664
$$

が次回も再現すると仮定した場合：

| NI Margin |    Feasibility |
| --------: | -------------: |
|      0.10 |           達成不可 |
|      0.20 |           達成不可 |
|      0.30 |           達成不可 |
|      0.40 | 約703,610 users |
|      0.50 | 約174,734 users |

これは、

> Targeting signalが見つかったことと、そのpolicyを実務投入できるだけの証拠を得られることは別問題

であることを示しています。

---

# Tech Stack

### SQL / Data Warehouse

* BigQuery
* GoogleSQL

### Python

* pandas
* NumPy
* SciPy
* statsmodels
* scikit-learn
* google-cloud-bigquery

### Statistical Methods

* Sample Ratio Mismatch
* Standardized Mean Difference
* Intent-to-Treat
* Difference in Proportions
* Welch Inference
* Bootstrap Confidence Interval
* Holm Multiple Testing Correction
* Treatment × Moderator Interaction
* HC3 Robust Standard Error
* T-Learner
* Qini / AUUC
* Inverse Propensity Weighting
* Policy Evaluation
* Non-inferiority Testing
* Power Analysis

---

# Repository Structure

```text
.
├── README.md
├── data
│   ├── processed
│   └── raw
│       └── Hillstrom.csv
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

---

# BigQuery Tables

主要table：

```text
ceus.hillstrom_raw
ceus.experiment_population
ceus.ab_metrics
ceus.segment_metrics
ceus.segment_lifts
```

SQLはBigQuery Standard SQL / GoogleSQLで記述しています。

---

# Reproduce

## 1. Python Environment

例：

```bash
python -m venv venv
source venv/bin/activate
```

必要packageをinstallします。

```bash
pip install \
  pandas \
  numpy \
  scipy \
  statsmodels \
  scikit-learn \
  google-cloud-bigquery
```

Google Cloud authenticationを完了した状態で実行します。

---

## 2. Data Audit

```bash
bq query \
  --use_legacy_sql=false \
  < sql/00_data_audit.sql
```

---

## 3. Randomization Validation

```bash
python src/validate_randomization.py
```

---

## 4. Experiment Population

```bash
bq query \
  --use_legacy_sql=false \
  < sql/01_experiment_population.sql
```

---

## 5. A/B Metrics

```bash
bq query \
  --use_legacy_sql=false \
  < sql/02_ab_metrics.sql
```

---

## 6. ATE Estimation

```bash
python src/estimate_ate.py
```

---

## 7. Segment Analysis

```bash
bq query \
  --use_legacy_sql=false \
  < sql/03_segment_analysis.sql
```

---

## 8. Heterogeneity

```bash
python src/heterogeneity.py
```

---

## 9. Uplift Modeling

```bash
python src/uplift_model.py \
  --project hillstrom-experiment-20260828 \
  --table ceus.experiment_population
```

---

## 10. Policy Evaluation

```bash
python src/policy_evaluation.py
```

---

## 11. Power Analysis

Base scenario：

```bash
python src/power_analysis.py
```

Historical policy differenceを再現すると仮定したsensitivity：

```bash
python src/power_analysis.py \
  --ni-assumed-true-difference -0.300664
```

---

# Main Outputs

## Randomization

```text
data/processed/
├── randomization_treatment_counts.csv
├── randomization_pairwise_balance.csv
├── randomization_covariate_summary.csv
└── randomization_validation_summary.json
```

## Average Treatment Effect

```text
data/processed/
├── ate_estimates.csv
└── ate_summary.json
```

## Uplift

```text
data/processed/
├── uplift_model_metrics.csv
├── uplift_top_k.csv
├── uplift_curves.csv
├── uplift_predictions.csv
└── uplift_summary.json
```

## Policy

```text
data/processed/
├── policy_evaluation.csv
├── policy_break_even.csv
└── policy_summary.json
```

## Power

```text
data/processed/
├── power_mde_sensitivity.csv
├── power_noninferiority_sensitivity.csv
└── power_summary.json
```

---

# Documentation

分析上の詳細は以下に分離しています。

### Decision Memo

[`docs/decision_memo.md`](docs/decision_memo.md)

> 分析結果から何を意思決定するか。

### Methodology

[`docs/methodology.md`](docs/methodology.md)

> 各分析をどの統計手法・設計思想で実施したか。

### Experiment Design

[`docs/experiment_design.md`](docs/experiment_design.md)

> Women's Top-10% targetingを次回RCTでどうprospective validationするか。

---

# Analytical Guardrails

本プロジェクトでは、分析結果を過大解釈しないため以下を明示的なルールとしています。

* SRM / covariate balanceだけで「randomization成功」と断定しない
* Men's EmailとWomen's Emailを直接比較していないため、どちらが統計的に優れているか断定しない
* Post-treatment variableでsegmentを作らない
* Conversionしたユーザーだけに限定してSpendを比較しない
* Descriptive subgroup review後のinteractionをconfirmatoryと呼ばない
* Predicted upliftをindividual causal effectそのものと解釈しない
* Training dataでuplift policyを評価しない
* Held-outで最良だったTop-kを即production policyにしない
* SpendをProfitと呼ばない
* Sample sizeを小さくするためにnon-inferiority marginを変更しない

---

# Limitations

主な制約は以下です。

### Profit informationがない

Datasetには、

* Gross margin
* Email delivery cost
* Contribution margin

が存在しません。

そのため最終的なprofit-optimal policyまでは決定できません。

### Individual Treatment Effectは観測できない

Uplift modelが出すscoreはCATE rankingの推定値であり、各ユーザーの真のIndividual Treatment Effectを直接観測しているわけではありません。

### Top-10% policyはpost-selectionされている

Top-10%は既存held-out analysisを確認した後に有望と判断したpolicyです。

そのためproduction deployment前に独立したprospective validationが必要です。

### Spendの分散が大きい

Spendはzero-inflatedかつheavy-tailedであり、小さなpolicy differenceを精度良く検証するには大きなsample sizeが必要です。

---

# Final Takeaway

この分析では、

> **A/B Testで平均効果が有意だった**

ところで終了していません。

Men's EmailとWomen's Emailはいずれも平均的には有効でした。

しかし、

* 誰に強く効くのか
* Uplift modelでそのユーザーを識別できるのか
* Targetingした場合にSend Allより価値があるのか
* Delivery costを考えるとdecisionが変わるのか
* そのpolicyを次回RCTで検証できるのか

まで評価すると、最終判断は異なります。

**Men's EmailはSend Allを維持。**

**Women's Emailも現時点ではSend Allを維持し、Top-10% targetingはprospective validation対象とする。**

このプロジェクトでは、

$$
Experiment
\rightarrow
Causal\ Inference
\rightarrow
Causal\ ML
\rightarrow
Policy\ Evaluation
\rightarrow
Business\ Decision
$$

を一貫した分析pipelineとして実装しています。
