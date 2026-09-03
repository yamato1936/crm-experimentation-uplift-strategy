# Prospective Experiment Design

## 1. 目的

本ドキュメントでは、既存分析から得られたWomen's Email targeting仮説を、新しいrandomized experimentでprospectiveに検証するための設計を定義します。

既存分析ではWomen's Emailについて、以下が確認されています。

- Controlに対する正の平均処置効果
- 一部pre-treatment covariateによるTreatment Effect Heterogeneity
- Uplift modelによるpositive ranking signal
- Top-k targetingによる配信効率改善の可能性

一方、Top-k targetingがSend Allより高いgross spendを生むことは確認できていません。

したがって次回実験では、**Women's Emailを全eligible userに送るSend Allと、事前に固定したTop-10% targeting policyを比較し、許容可能なSpend lossの範囲内で配信量を削減できるか**を検証します。

## 2. Primary Business Question

> Women's Emailをeligible user全員に送る代わりに、事前に固定したuplift modelによって上位10%のユーザーだけに送ることで、Spend per randomized userを事業上許容可能な範囲に維持しながら配信量を削減できるか？

本実験の主目的はtargeting policyがSend Allより有意に高いSpendを生むことの証明ではありません。

配信量を約90%削減するpolicyであるため、一定のSpend lossを許容したうえでの**non-inferiority**を主要な意思決定フレームとします。

## 3. Experiment Arms

### Arm A: Send All

Eligible user全員にWomen's Emailを配信します。

```text
policy_A(x) = 1
```

### Arm B: Frozen Top-10% Targeting

既存データで学習したuplift modelを用いてuplift scoreを計算し、事前に固定したルールで上位約10%のユーザーのみにWomen's Emailを配信します。

```text
if predicted_uplift(x) >= frozen_threshold:
    send Women's Email
else:
    send no email
```

Arm B内でTop-10%に入らなかったユーザーにはEmailを配信しません。

## 4. Randomization Unit

Randomization unitはeligible userです。

同一ユーザーが複数armに入らないよう、user-levelでArm A / Arm Bへ割り付けます。

推奨allocation ratio:

```text
1 : 1
```

## 5. Eligibility Criteria

実験対象者は少なくとも以下を満たすユーザーとします。

- Women's Email campaignの配信対象としてbusiness上eligible
- Uplift scoringに必要なpre-treatment featureが利用可能
- Experiment開始前にTreatment assignment可能
- Outcome measurement期間を定義可能

Model featureにはpre-treatment variableのみを使用します。

## 6. Frozen Policy

本実験の最重要ルールは、**Outcomeを見る前にtargeting policyを完全に固定すること**です。

Experiment開始前に以下をfreezeします。

### Feature Set

- `recency`
- `history`
- `history_segment`
- `mens`
- `womens`
- `zip_code`
- `newbie`
- `channel`

### Model

Women's Email vs ControlのT-Learner。

### Model Parameters

Random Forestを含む全hyperparametersを固定します。

### Scoring Logic

```text
predicted_uplift(x)
= predicted_outcome_treatment(x)
- predicted_outcome_control(x)
```

### Target Fraction

```text
10%
```

### Threshold

Experiment対象populationに対するuplift score rankingからTop-10%を決定する具体的ルールを事前に固定します。Tie handlingも事前に定義します。

## 7. Policy Selectionに関する注意

Top-10% policyは既存held-out analysisで有望なsignalを確認した後に選択されています。

したがって既存分析におけるTop-10%成績は**exploratory evidence**です。

新しいindependent RCTを開始する前にpolicyをfreezeすることで、次回実験ではそのpolicyをprospectiveに検証できます。

Experiment開始後に以下を変更しません。

- Top-20%への変更
- 別modelへの変更
- Feature追加
- Threshold変更
- Outcomeを見ながらmodelを再学習

## 8. Primary Outcome

Primary Outcomeは**Spend per randomized user**です。

Conversionの有無にかかわらず、全randomized userを分析対象に含めます。

Conversionしたユーザーだけに限定したSpend分析は行いません。

## 9. Primary Estimand

```text
Delta
= E[Spend | Frozen Targeting]
- E[Spend | Send All]
```

これはpolicy-level Intent-to-Treat estimandです。

Arm Bで実際にEmailを受け取るユーザーが約10%だけであっても、Arm Bへrandomizeされた全ユーザーを分母に含めます。

## 10. Primary Hypothesis

Non-inferiority marginを`Margin > 0`とします。

```text
H0: Delta <= -Margin
H1: Delta >  -Margin
```

つまり、TargetingによるSpend lossが事前に定めた最大許容lossより小さいかを検証します。

## 11. Non-inferiority Margin

Marginは統計的に都合の良い値ではなく、**business toleranceから決める**必要があります。

既存分析におけるsample-size sensitivity:

| NI Margin | Total N: true difference = 0 |
| ---: | ---: |
| 0.10 | 694,298 |
| 0.20 | 173,576 |
| 0.30 | 77,146 |
| 0.40 | 43,394 |
| 0.50 | 27,772 |

必要Nが小さいという理由だけでmarginを大きくしてはいけません。

Margin決定には少なくとも以下が必要です。

- Gross margin
- Email delivery cost
- Campaign operational cost
- Opportunity cost
- Business risk tolerance

## 12. Economic Decision Rule

Spendはrevenue-like metricであり、Profitではありません。

実務では次のようなnet valueで評価します。

```text
Net Value
= Gross Margin * Spend
- Delivery Cost
```

TargetingとSend Allのdifferenceは概念的に次の形です。

```text
Delta Net Value
= Gross Margin * Delta Spend
+ Delivery Cost Saving
```

Top-10% targetingでは約90%の配信削減が可能なため、一定のSpend lossが存在してもdelivery cost savingによってnet valueではTargetingが優位になる可能性があります。

## 13. Historical Evidence

既存held-out analysisのWomen's Email Top-10% policy:

```text
Send All policy value = 1.156
Top-10% policy value  = 0.855
Difference            = -0.301
95% CI                = [-0.745, +0.114]
```

CIは0を跨いでいるため、Top-10%がSend Allと同等であるとも、明確に劣るとも確定できません。

この結果は次回experiment designのhistorical contextとして使用しますが、prospective hypothesis testの結果として再利用しません。

## 14. Historical Break-even Analysis

Women's Email Top-10%のSend Allに対するpoint-estimate break-even delivery costは約0.334 revenue-units / emailでした。

これはprofit thresholdではありません。Formal business decisionには実際のgross marginとdelivery costを使用します。

## 15. Secondary Outcomes

Primary hypothesisを変更しない範囲で以下をsecondary outcomeとして確認します。

- Conversion Rate
- Visit Rate
- Email Volume
- Total Spend
- Spend per Email Sent

`Spend per Email Sent`はoperational efficiencyの参考指標であり、primary causal estimandではありません。

## 16. Primary Analysis

Intent-to-Treatで実施します。

```text
estimated_Delta
= mean_spend_ArmB
- mean_spend_ArmA
```

Primary conclusionはone-sided confidence boundと事前定義したnon-inferiority marginの関係で判断します。

Non-inferiority成立条件:

```text
lower confidence bound > -Margin
```

## 17. Variance Estimation

Spendはzero-inflatedかつheavy-tailedです。

Robustness check候補:

- Welch-type robust inference
- Heteroskedasticity-robust standard error
- Bootstrap confidence interval

Primary analysis methodはExperiment開始前に固定します。

## 18. Covariate Adjustment

Randomizationによりunadjusted ITT estimatorは因果推論上妥当です。

一方、Spendの分散が大きいため、precision improvementを目的としてpre-treatment covariatesによるadjustmentを検討します。

```text
Spend
= intercept
+ policy_arm_effect
+ pre_treatment_covariates
+ error
```

CovariatesはExperiment開始前に固定し、Outcomeを見た後に都合の良い変数だけを選択しません。

Candidate covariates:

- `recency`
- `history`
- `history_segment`
- `mens`
- `womens`
- `zip_code`
- `newbie`
- `channel`

## 19. Sample Size Planning

Historical held-out SD:

```text
Women's Email SD = 16.76
Control SD       = 10.25
Planning SD      = 16.76
```

大きい方をconservative planning valueとして使用します。

### Two-sided MDE sensitivity

| Spend/User MDE | Total N |
| ---: | ---: |
| 0.10 | 881,424 |
| 0.20 | 220,356 |
| 0.30 | 97,936 |
| 0.40 | 55,090 |
| 0.50 | 35,258 |

### Non-inferiority sensitivity: true difference = 0

| NI Margin | Total N |
| ---: | ---: |
| 0.10 | 694,298 |
| 0.20 | 173,576 |
| 0.30 | 77,146 |
| 0.40 | 43,394 |
| 0.50 | 27,772 |

## 20. Historical Effect Sensitivity

Historical point estimate:

```text
Delta = -0.300664
```

これがtrue effectに近いと仮定すると:

| NI Margin | Feasibility |
| ---: | ---: |
| 0.10 | 達成不可 |
| 0.20 | 達成不可 |
| 0.30 | 達成不可 |
| 0.40 | Total N 約703,610 |
| 0.50 | Total N 約174,734 |

これは、小さいmarginでnon-inferiorityを証明することが困難である可能性を示します。

## 21. Randomization Checks

Outcome分析前に以下を確認します。

- Sample Ratio Mismatch
- Pre-treatment covariate balance
- Send All armのdelivery fidelity
- Targeting armのTop-10% policy fidelity

Balance resultを見てexperiment sampleを恣意的に変更しません。

## 22. Implementation Fidelity

最低限、以下をlogとして保存します。

- randomized arm
- uplift score
- frozen threshold
- targeting decision
- actual send flag
- send timestamp
- model version
- feature version
- experiment version

これによりstatistical designとproduction implementationの問題を切り分けます。

## 23. Missing Data

Randomization後のmissing outcomeが発生した場合、missingnessをArm別に確認します。

Treatment assignmentによってmissingnessが異なる場合、単純なcomplete-case analysisにはbiasの可能性があります。

Missing-data handling ruleはExperiment開始前に定義します。

## 24. Multiple Testing

Primary testは1つに固定します。

> Women's Frozen Top-10% Targeting vs Send AllのSpend non-inferiority

Visit / Conversionなどのsecondary outcomesはprimary decisionと分離します。Formal significance claimを行う場合はmultiple-testing correctionを適用します。

## 25. Decision Criteria

### Targetingを採用できる条件

1. Primary non-inferiority criterionを満たす
2. Frozen policyがproduction上正しく実装されている
3. 配信削減量が想定通りである
4. Gross margin / delivery costを含めたnet valueがSend All以上
5. Customer experience上の重大な悪化がない

### Send Allを維持する条件

- Non-inferiorityを示せない
- Net valueがSend Allを下回る
- Targeting implementationが不安定
- Experiment power不足で結論不能

## 26. Failure to Rejectの解釈

Non-inferiorityを示せなかった場合、TargetingがSend Allより劣ると証明されたとは限りません。

- **Clear Inferiority:** Confidence intervalがNI marginより明確に悪い
- **Inconclusive:** Confidence intervalが広くNI boundaryを跨ぐ

後者は`Evidence insufficient`と判断します。

## 27. Experiment Stop Rules

Defaultはfixed-sample designです。

途中結果を繰り返し確認し、有意になった時点で停止する運用は行いません。

Sequential designを使用する場合は、interim timing、alpha spending、stop boundary、futility ruleを事前に定義します。

## 28. Pre-registration Checklist

Experiment開始前に以下を確定します。

- [ ] Eligible population
- [ ] Randomization unit
- [ ] Arm allocation
- [ ] Frozen uplift model
- [ ] Model version
- [ ] Feature definitions
- [ ] Top-10% targeting rule
- [ ] Tie handling
- [ ] Primary outcome
- [ ] Outcome measurement window
- [ ] Primary estimand
- [ ] NI margin
- [ ] Alpha
- [ ] Power
- [ ] Required sample size
- [ ] Covariate adjustment specification
- [ ] Missing-data handling
- [ ] Secondary outcomes
- [ ] Multiple-testing rule
- [ ] Business net-value equation
- [ ] Gross margin assumption
- [ ] Delivery cost
- [ ] Final decision threshold

すべてOutcome観測前に確定します。

## 29. Current Recommendation

現時点では、**Women's EmailのSend Allをproduction baselineとして維持する**のが妥当です。

Top-10% targetingは`promising but unvalidated policy`として扱います。

Business-justified non-inferiority marginと実行可能なsample sizeを確定できた場合のみprospective RCTへ進みます。

## 30. Experiment Summary

| Item | Design |
| --- | --- |
| Control Policy | Send All |
| Candidate Policy | Frozen Women's Email Top-10% Uplift Targeting |
| Primary Outcome | Spend per randomized user |
| Primary Framework | Non-inferiority |
| Randomization | 1:1 user-level randomization |
| Targeting Rate | 約10% |
| Analysis Principle | Intent-to-Treat |
| Model Rule | Experiment開始前に完全freeze |

Final decisionはstatistical significanceだけでなく、**statistical evidence + delivery cost + gross margin + operational feasibility**を統合して判断します。
