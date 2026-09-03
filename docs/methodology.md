# Methodology

## 1. 分析目的

本プロジェクトでは、Hillstrom Email Marketing Datasetを用いて、CRMキャンペーンの因果効果とtargeting policyの意思決定価値を評価します。

> CRMキャンペーンは本当にユーザー行動を改善したのか。全員に配信すべきか。それとも効果のあるユーザーだけに配信すべきか？

分析フロー:

1. Data Quality Audit
2. Randomization Validation
3. Experiment Population
4. A/B Metrics
5. Average Treatment Effect
6. Treatment Effect Heterogeneity
7. Uplift Modeling
8. Policy Evaluation
9. Prospective Experiment Design
10. Power / Feasibility Analysis

目的は単に予測精度の高いモデルを作ることではなく、**因果推論からbusiness decisionまで一貫した分析フローを構築すること**です。

## 2. データ

観測単位はユーザーで、総行数は64,000です。

Treatment:

- `No E-Mail`
- `Mens E-Mail`
- `Womens E-Mail`

分析用label:

- `control`
- `mens_email`
- `womens_email`

主要Outcome:

- `visit`
- `conversion`
- `spend`

Spendはconversionしたユーザーだけに限定せず、**全randomized userを分母としたSpend per randomized user**として評価します。Conversionはpost-treatment variableであるため、conversion条件付きのSpend比較は行いません。

## 3. Pre-treatment Covariates

Treatment assignment以前に決まっている以下の変数のみをcovariateとして使用します。

- `recency`
- `history`
- `history_segment`
- `mens`
- `womens`
- `zip_code`
- `newbie`
- `channel`

`visit`、`conversion`、`spend`はpost-treatment outcomeなのでmodel featureには使用しません。

## 4. Data Quality Audit

`sql/00_data_audit.sql` で以下を確認します。

- Row count
- Missingness
- Treatment domain
- Binary variable domain
- Numeric range
- Outcome consistency
- Duplicate-like row patterns

明示的なcustomer IDは存在しないため、全observed columnsが一致する行だけを理由にduplicate customerとは判断せず、削除しません。

## 5. Randomization Validation

`src/validate_randomization.py` でSample Ratio Mismatchとpre-treatment covariate balanceを確認します。

### Sample Ratio Mismatch

3群が1:1:1で割り付けられているという帰無仮説に対してchi-square testを実施します。

```text
H0: p_control = p_mens = p_womens = 1/3
```

結果:

```text
Chi-square = 0.203
p-value    = 0.904
```

SRMを示す証拠は確認されませんでした。

### Standardized Mean Difference

連続変数のpairwise SMDは次の形で計算します。

```text
SMD = (mean_treatment - mean_control)
      / sqrt((variance_treatment + variance_control) / 2)
```

Binary / categorical covariatesもlevel indicatorベースで評価します。

最大absolute SMDは約0.017で、`|SMD| >= 0.10`となるcovariateはありませんでした。

これはrandomizationの成功を証明するものではなく、**SRMや重大なobserved covariate imbalanceを示す証拠が確認されなかった**というdiagnostic resultです。

## 6. Experiment Population

`sql/01_experiment_population.sql` でcanonical populationを構築します。

BigQuery table:

```text
ceus.experiment_population
```

Treatment normalization:

```text
No E-Mail      -> control
Mens E-Mail    -> mens_email
Womens E-Mail  -> womens_email
```

Eligibility flags:

- `treatment_eligible`
- `pretreatment_eligible`
- `visit_eligible`
- `conversion_eligible`
- `spend_eligible`
- `outcome_consistent`
- `experiment_eligible`

`experiment_eligible`はTreatmentとpre-treatment covariatesの妥当性のみで定義し、outcome eligibilityはmetric-specificに管理します。

## 7. A/B Metrics

`sql/02_ab_metrics.sql` ではdescriptive metricsのみを作成します。

- N
- Visit count / rate
- Conversion count / rate
- Total Spend
- Mean Spend per randomized user
- Standard deviation

SQLではp-valueやconfidence intervalを計算せず、記述統計と推測統計の責務を分離します。

## 8. Average Treatment Effect

`src/estimate_ate.py` で以下の6つのITT effectを推定します。

```text
2 treatment comparisons x 3 outcomes = 6 tests
```

Comparisons:

- Men's Email vs Control
- Women's Email vs Control

Outcomes:

- Visit
- Conversion
- Spend

### Binary Outcomes

Visit / Conversionではdifference in proportionsを推定します。

```text
ATE = treatment_rate - control_rate
```

Confidence intervalはunpooled SEを使い、hypothesis testはpooled null varianceによるtwo-proportion z-testを使います。

### Spend

Spendではdifference in meansを推定します。

```text
ATE = mean_spend_treatment - mean_spend_control
```

群間で分散が異なる可能性を考慮してWelch inferenceを使用し、zero-inflated / heavy-tailed distributionへのrobustness checkとしてpercentile bootstrap CIも計算します。

### Multiple Testing

事前定義した6比較にHolm correctionを適用し、Family-Wise Error Rateを制御します。

## 9. Segment Analysis

`sql/03_segment_analysis.sql` でpre-treatment covariates別のdescriptive liftを作成します。

対象:

- `recency`
- `history_segment`
- `mens`
- `womens`
- `newbie`
- `channel`
- `zip_code`

目的はhypothesis generationです。Raw subgroup liftだけでheterogeneityを断定しません。

## 10. Treatment Effect Heterogeneity

`src/heterogeneity.py` ではinteraction modelを推定します。

```text
Y = beta0 + beta1*T + beta2*X + beta3*(T*X) + error
```

Treatment effect heterogeneityはinteraction coefficient `beta3` で評価します。

OLSにHC3 robust standard errorを使用し、binary outcomeではLinear Probability Modelとしてoriginal outcome scaleで解釈します。

Targeted follow-up family:

- Women's Email x `womens`
- Men's Email x `mens`
- Visit / Conversion / Spend
- 合計6 tests

このfamilyにはHolm correctionを適用します。ただしdescriptive subgroup review後にhypothesisを選択しているため、結果はconfirmatoryではなくexploratory / targeted follow-upとして解釈します。

`channel` interactionは別のexploratory familyとして扱います。

## 11. Uplift Modeling

`src/uplift_model.py` ではT-Learnerを構築します。

3-arm treatmentを1つのbinary problemにせず、以下を別々に扱います。

- Men's Email vs Control
- Women's Email vs Control

Treatment modelとControl modelを別々に学習し、predicted upliftを次の差として定義します。

```text
predicted_uplift(x)
= predicted_outcome_treatment(x)
- predicted_outcome_control(x)
```

Random Forestを使用し、pre-treatment covariatesのみをfeatureにします。

Train / held-out test splitを行い、training dataでpolicy performanceを評価しません。

Primary evaluation metrics:

- Qini
- AUUC
- Uplift@10%
- Uplift@20%
- Uplift@30%
- Uplift@50%

通常のAUC / RMSEをprimary metricにしない理由は、目的がoutcome predictionではなくtreatment effect rankingだからです。

Predicted upliftは各ユーザーの真のIndividual Treatment Effectではなく、model-based estimateとして扱います。

## 12. Policy Evaluation

`src/policy_evaluation.py` で以下のpolicyをheld-out observations上で比較します。

- Send None
- Send All
- Top 10%
- Top 20%
- Top 30%
- Top 50%

Policy valueはInverse Propensity Weightingで推定します。

```text
V(policy)
= E[
    policy(X) * T * Y / e
    + (1 - policy(X)) * (1 - T) * Y / (1 - e)
  ]
```

BootstrapはTreatment assignment内でstratifiedに実施します。このbootstrapは**既に学習済みのmodelを固定した条件下でのevaluation uncertainty**を評価し、model retraining uncertaintyは含みません。

同じheld-out sample上で最良だったTop-kをproduction-optimal policyとは呼ばず、prospective validation対象とします。

## 13. Break-even Delivery Cost

Spend outcomeではdelivery costを考慮したpolicy comparisonを行います。

```text
Net Value(policy, cost)
= Policy Value - cost * treatment_rate
```

Send Allとtargetingのbreak-even thresholdを計算します。

Hillstrom Datasetにはgross margin、delivery cost、profit情報がないため、算出値は**revenue-equivalent break-even threshold**としてのみ解釈します。

実務では以下の形で評価すべきです。

```text
Net Value = Gross Margin * Incremental Spend - Delivery Cost
```

## 14. Prospective Experiment Design

Women's Top-10% targetingはproductionへ即導入せず、prospective RCTでvalidationします。

- Arm A: Send All
- Arm B: Frozen Top-10% Targeting Policy

Experiment開始前にfeature set、model type、hyperparameters、trained model、scoring rule、target fraction、thresholdをfreezeします。

Primary estimand:

```text
Delta = E[Spend | Targeting] - E[Spend | Send All]
```

## 15. Power Analysis

`src/power_analysis.py` でtwo-sided MDEとnon-inferiority marginに対するsample-size sensitivityを計算します。

Planning SDはheld-out treatment / control SDの大きい方を使用します。

```text
planning_sd = max(sd_treatment, sd_control)
```

Two-sided equal-allocation approximation:

```text
n_per_arm
= 2 * sigma^2 * (z_alpha + z_power)^2 / delta^2
```

Non-inferiority:

```text
H0: Delta <= -Margin
H1: Delta >  -Margin
```

Marginは必要sample sizeの都合で決めず、gross margin、delivery cost、opportunity cost、business toleranceから事前に決めるbusiness parameterです。

## 16. Multiple Testing Policy

すべてのp-valueを1つの巨大なfamilyとして扱わず、analysis objectiveごとにfamilyを分離します。

### ATE Family

- 2 treatment comparisons
- 3 outcomes
- 6 tests
- Holm correction

### Targeted Follow-up Heterogeneity Family

- 2 treatment-moderator hypotheses
- 3 outcomes
- 6 tests
- Holm correction
- Post-selectionのためexploratory interpretationを維持

### Exploratory Channel Family

別familyとして評価します。

## 17. Analytical Guardrails

- Randomizationが「成功した」と断定しない
- Men's EmailとWomen's Emailを直接比較していないため、どちらが統計的に優れているか断定しない
- Post-treatment variableをheterogeneity / uplift featureに使わない
- Conversionしたユーザーだけに限定してSpendを比較しない
- Descriptive subgroup review後のinteractionをconfirmatoryと呼ばない
- Predicted upliftをindividual causal effectそのものと解釈しない
- Training dataでpolicyを評価しない
- Held-outで最良だったTop-kを即production policyにしない
- SpendをProfitと呼ばない
- Sample sizeを小さくするためにNI marginを広げない

## 18. Reproducibility

```bash
bq query --use_legacy_sql=false < sql/00_data_audit.sql

python src/validate_randomization.py \
  --project hillstrom-experiment-20260828 \
  --table ceus.hillstrom_raw

bq query --use_legacy_sql=false < sql/01_experiment_population.sql
bq query --use_legacy_sql=false < sql/02_ab_metrics.sql

python src/estimate_ate.py \
  --project hillstrom-experiment-20260828 \
  --table ceus.experiment_population

bq query --use_legacy_sql=false < sql/03_segment_analysis.sql

python src/heterogeneity.py

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

## 19. Methodological Summary

本プロジェクトでは次の順序で分析を構築しました。

```text
Data Quality
    -> Randomization Validation
    -> ATE
    -> Heterogeneity
    -> Uplift
    -> Policy Evaluation
    -> Prospective Experiment Design
```

目的は「Treatment effectが有意だった」で終了することではなく、**誰に施策を実行すべきか、そのpolicyに本番導入できるだけの証拠があるか、次回検証にどの程度のsample sizeが必要か**まで接続することです。
