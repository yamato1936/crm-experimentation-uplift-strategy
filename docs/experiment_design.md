# Prospective Experiment Design

## 1. 目的

本ドキュメントでは、Hillstrom Email Marketing Datasetを用いた既存分析から得られた仮説を、**新しいランダム化比較試験でprospectiveに検証するための実験設計**を定義する。

既存分析ではWomen's Emailについて、

* Controlに対する正の平均処置効果
* 一部pre-treatment covariateによるTreatment Effect Heterogeneity
* Uplift modelによるpositive ranking signal
* Top-k targetingによる配信効率改善の可能性

が確認された。

一方で、Top-k targetingがSend Allより高いgross spendを生み出すことは確認できていない。

したがって次回実験では、

> Women's Emailを全員に送る現行方針と比較して、事前に固定したuplift targeting policyが、許容可能なSpend lossの範囲内で配信量を削減できるか

を検証する。

---

## 2. Primary Business Question

> Women's Emailをeligible user全員に送る代わりに、事前に固定したuplift modelによって上位10%のユーザーだけに送ることで、Spend per randomized userを事業上許容可能な範囲に維持しながら、配信量を削減できるか？

本実験の主目的は、

> targeting policyがSend Allより「有意に高いSpend」を生むこと

を証明することではない。

配信量を約90%削減するpolicyであるため、一定のSpend lossを許容した上での**non-inferiority**を主要な意思決定フレームとする。

---

## 3. Experiment Arms

### Arm A: Send All

eligible user全員にWomen's Emailを配信する。

$$
\pi_A(x)=1
$$

全ユーザーがTreatmentを受けるpolicyである。

---

### Arm B: Frozen Top-10% Targeting

既存データで学習済みのuplift modelを用いてuplift scoreを計算し、事前に固定したルールに基づいて上位約10%のユーザーのみにWomen's Emailを配信する。

$$
\pi_B(x)
=
\begin{cases}
1 & \hat\tau(x)\ge c \\
0 & \hat\tau(x)<c
\end{cases}
$$

ここで、

* \(\hat\tau(x)\): frozen uplift modelによるpredicted uplift
* \(c\): 実験開始前に固定したTop-10% threshold

とする。

Arm B内でTop-10%に入らなかったユーザーにはEmailを配信しない。

---

## 4. Randomization Unit

Randomization unitは、

> eligible user

とする。

同一ユーザーが複数armに入らないよう、ユーザー単位でArm A / Arm Bへ割り付ける。

推奨allocation ratioは、

$$
1:1
$$

とする。

---

## 5. Eligibility Criteria

実験対象者は、少なくとも以下を満たすユーザーとする。

* Women's Email campaignの配信対象としてbusiness上eligible
* uplift scoringに必要なpre-treatment featureが利用可能
* Experiment開始前にTreatment assignment可能
* Outcome measurement期間を定義可能

既存分析と同様、model featureにはpre-treatment variableのみを使用する。

---

## 6. Frozen Policy

本実験の最重要ルールは、

> Outcomeを見る前にtargeting policyを完全に固定する

ことである。

以下をexperiment開始前にfreezeする。

### Feature Set

* `recency`
* `history`
* `history_segment`
* `mens`
* `womens`
* `zip_code`
* `newbie`
* `channel`

### Model

既存分析で使用したWomen's Email vs ControlのT-Learner。

### Treatment Definition

* Treatment: Women's Email
* Control action within targeting policy: No Email

### Model Parameters

Random Forestを含む全hyperparameterを固定する。

### Scoring Logic

$$
\hat\tau(x)
=
\hat\mu_1(x)-\hat\mu_0(x)
$$

を変更しない。

### Target Fraction

$$
10\%
$$

に固定する。

### Threshold

実験対象populationに対するuplift score rankingからTop-10%を決定する具体的なルールを事前に固定する。

tieが発生する場合の処理方法も事前に定義する。

---

## 7. Policy Selectionに関する注意

Top-10% policyは、既存held-out analysisで有望なsignalが観測された後に選択された。

したがって、既存分析におけるTop-10%の成績は**exploratory evidence**である。

しかし、新しい独立したRCTを開始する前にpolicyをfreezeすれば、次回実験ではそのpolicyをprospectiveに検証できる。

実験開始後に、

* Top-20%へ変更
* 別モデルへ変更
* Featureを追加
* Thresholdを変更
* Outcomeを見ながらmodelを再学習

してはならない。

---

## 8. Primary Outcome

Primary Outcomeは、

> Spend per randomized user

とする。

各ユーザーについて実験期間中のSpendを測定し、conversionの有無にかかわらず全randomized userを分析対象に含める。

$$
Y_i=Spend_i
$$

とする。

conversionしたユーザーだけに限定しない。

---

## 9. Primary Estimand

Primary estimandは、

$$
\Delta
=
E[Y\mid Arm\ B]
-
E[Y\mid Arm\ A]
$$

すなわち、

$$
\Delta
=
E[Spend\mid Frozen\ Targeting]
-
E[Spend\mid Send\ All]
$$

とする。

これはpolicy-level Intent-to-Treat estimandである。

Arm Bで実際にEmailを受け取るユーザーが約10%だけであっても、Arm Bへrandomizeされた全ユーザーを分母に含める。

---

## 10. Primary Hypothesis

Non-inferiority marginを、

$$
M>0
$$

とする。

Hypothesisは、

$$
H_0:
\Delta\le -M
$$

$$
H_1:
\Delta>-M
$$

と定義する。

つまり、

> TargetingによるSpend lossが、事前に定めた最大許容loss \(M\) より小さいか

を検証する。

---

## 11. Non-inferiority Margin

\(M\) は統計的に都合の良い値ではなく、**business toleranceから決める**。

既存分析では以下のmarginについてsample-size sensitivityを確認した。

| NI Margin | True Difference = 0を仮定したTotal N |
| --------: | ------------------------------: |
|      0.10 |                         694,298 |
|      0.20 |                         173,576 |
|      0.30 |                          77,146 |
|      0.40 |                          43,394 |
|      0.50 |                          27,772 |

ただし、必要Nが小さいという理由だけでmarginを大きくしてはならない。

margin決定には少なくとも以下が必要である。

* Gross margin
* Email delivery cost
* Campaign operational cost
* Customer contact cost
* Opportunity cost
* Business risk tolerance

---

## 12. Economic Decision Rule

Spendは売上に近い指標であり、Profitではない。

実務上は、

$$
NetValue
=
GrossMargin
\times
Spend
-
DeliveryCost
$$

を評価すべきである。

Send AllとTargetingのnet value差は、

$$
\Delta NetValue
=
m\Delta Spend
+
c(1-r)
$$

と表現できる。

ここで、

* \(m\): Gross margin
* \(c\): 1通あたりdelivery cost
* \(r\): Targeting policyの配信率

Top-10% policyでは、

$$
r\approx0.10
$$

であるため、約90%の配信削減効果がある。

したがって、一定のSpend lossが存在しても、delivery cost savingによってnet valueではTargetingが優位になる可能性がある。

---

## 13. Historical Evidence

既存held-out analysisにおけるWomen's Email Top-10% policyの結果は以下であった。

### Gross Spend Policy Value

Send All:

$$
1.156
$$

Top-10%:

$$
0.855
$$

Difference:

$$
Top10-SendAll=-0.301
$$

95% CI:

$$
[-0.745,\ 0.114]
$$

このCIは0を跨いでいるため、

> Top-10%がSend Allと同等である

とも、

> Send Allより劣る

とも確定できない。

この結果は次回実験を設計するためのhistorical contextとして使用するが、prospective hypothesis testの結果として再利用しない。

---

## 14. Historical Break-even Analysis

既存policy evaluationでは、Top-10% targetingとSend Allのbreak-even delivery cost point estimateは、

$$
c^*\approx0.334
$$

であった。

これは、

> Spendをそのまま経済価値として扱った場合、1配信あたり約0.334以上のコストが存在すると、Top-10% policyがSend Allよりnet valueで有利になる可能性がある

ことを意味する。

ただしgross marginが不明なため、これはprofit thresholdではない。

本実験の正式なbusiness decision ruleには、実際のmargin / delivery costを使用する。

---

## 15. Secondary Outcomes

Primary hypothesisを変更しない範囲で、以下をsecondary outcomeとして確認する。

### Conversion Rate

$$
P(Conversion=1)
$$

### Visit Rate

$$
P(Visit=1)
$$

### Email Volume

1 randomized userあたりのEmail配信数。

### Total Spend

Policy population全体の総Spend。

### Spend per Email Sent

Operational efficiencyの参考指標として、

$$
\frac{Total\ Spend}{Emails\ Sent}
$$

を計算できる。

ただしこれはprimary causal estimandではない。

---

## 16. Primary Analysis

Primary analysisはIntent-to-Treatで実施する。

Arm assignmentに基づき、

$$
\hat\Delta
=
\bar Y_B-\bar Y_A
$$

を推定する。

Primary conclusionは、

$$
\hat\Delta
$$

のone-sided confidence boundと事前定義したnon-inferiority margin \(M\) の関係で判断する。

Non-inferiorityが成立するには、confidence intervalの下限が、

$$
-M
$$

を上回る必要がある。

---

## 17. Variance Estimation

Spendはzero-inflatedかつheavy-tailedである。

したがって、normal approximationだけに依存せず、

* Welch-type robust inference
* Heteroskedasticity-robust standard error
* Bootstrap confidence interval

などによるrobustness checkを行う。

Primary analysis methodはexperiment開始前に固定する。

---

## 18. Covariate Adjustment

Randomizationによってunadjusted ITT estimatorは因果推論上妥当である。

一方、Spendの分散が大きいため、precision improvementを目的としてpre-treatment covariatesによるadjustmentを検討する。

基本形：

$$
Y_i
=
\alpha
+
\tau Z_i
+
\beta^\top X_i
+
\epsilon_i
$$

ここで、

* \(Z_i\): Arm B indicator
* \(X_i\): pre-treatment covariates
* \(\tau\): adjusted policy effect

とする。

Covariatesはexperiment開始前に固定する。

Outcomeを見た後に「効いた変数だけ」を選択しない。

---

## 19. Candidate Adjustment Covariates

既存データで利用可能な候補：

* `recency`
* `history`
* `history_segment`
* `mens`
* `womens`
* `zip_code`
* `newbie`
* `channel`

これらはTreatment assignment前に観測される。

Post-treatment variableは使用しない。

---

## 20. Sample Size Planning

既存held-out dataでは、

* Women's Email SD: 約16.76
* Control SD: 約10.25

であった。

保守的なplanning valueとして、

$$
\sigma_{plan}=16.76
$$

を使用した。

### Two-sided MDE Sensitivity

| Spend/User MDE | Total N |
| -------------: | ------: |
|           0.10 | 881,424 |
|           0.20 | 220,356 |
|           0.30 |  97,936 |
|           0.40 |  55,090 |
|           0.50 |  35,258 |

### Non-inferiority Sensitivity

True differenceを0と仮定した場合：

| NI Margin | Total N |
| --------: | ------: |
|      0.10 | 694,298 |
|      0.20 | 173,576 |
|      0.30 |  77,146 |
|      0.40 |  43,394 |
|      0.50 |  27,772 |

---

## 21. Historical Effectを仮定したSensitivity

既存held-out estimate、

$$
\Delta=-0.300664
$$

が真の効果に近いと仮定すると、

| NI Margin |      Feasibility |
| --------: | ---------------: |
|      0.10 |             達成不可 |
|      0.20 |             達成不可 |
|      0.30 |             達成不可 |
|      0.40 | Total N 約703,610 |
|      0.50 | Total N 約174,734 |

となった。

これは、現在のpoint estimateが再現する場合、小さいmarginでnon-inferiorityを証明することが困難であることを示す。

ただし、このhistorical estimateを次回experimentの真のeffectとして固定しない。

---

## 22. Randomization Checks

Experiment開始後、outcome分析前に以下を確認する。

### Sample Ratio Mismatch

Arm A / Arm Bのallocationが設計通りであるか確認する。

### Pre-treatment Balance

主要covariateについてSMDを確認する。

ただしbalance testの結果を見てexperiment sampleを恣意的に変更しない。

### Treatment Delivery

* Send All armで予定通り配信されたか
* Targeting armでTop-10%ルールが正しく適用されたか

を確認する。

---

## 23. Implementation Fidelity

Targeting policyの実験では、統計的randomizationだけでなくpolicy implementationの正確性が重要である。

最低限、以下をlogとして保存する。

* randomized arm
* uplift score
* frozen threshold
* targeting decision
* actual send flag
* send timestamp
* model version
* feature version
* experiment version

これにより、

> Randomizationは正しかったがproduction logicが違っていた

という問題を切り分けられるようにする。

---

## 24. Missing Data

Randomization後のmissing outcomeが発生した場合、missingnessをTreatment assignment別に確認する。

Outcome missingnessがTreatmentによって異なる場合、単純なcomplete-case analysisにはbiasの可能性がある。

Missing-data handling ruleはexperiment開始前に定義する。

可能な限り、randomized user全員についてSpendを0を含めて観測可能な設計とする。

---

## 25. Multiple Testing

### Primary Test

Primary testは、

> Women's Frozen Top-10% Targeting vs Send AllのSpend non-inferiority

の1つとする。

このprimary hypothesisについてalphaを確保する。

### Secondary Outcomes

Visit / Conversion等のsecondary outcomeはprimary decisionと分離する。

複数secondary hypothesisについてformal significance claimsを行う場合はHolm等のmultiple-testing correctionを適用する。

---

## 26. Decision Criteria

### Targetingを採用できる条件

最低限、以下を満たす必要がある。

1. Primary non-inferiority criterionを満たす
2. Frozen policyがproduction上正しく実装されている
3. 配信削減量が想定通りである
4. Gross margin / delivery costを含めたnet valueがSend All以上
5. Safety / customer experience上の重大な悪化がない

### Send Allを維持する条件

以下のいずれかの場合、Send Allを維持する。

* Non-inferiorityを示せない
* Net valueがSend Allを下回る
* Targeting implementationが不安定
* Experiment powerが不足して結論不能

### Send None

Women's Email自体がControlより正のATEを持つ既存証拠があるため、現在の主要候補ではない。

ただし将来的にdelivery costやbusiness constraintが大きく変化する場合は再評価する。

---

## 27. Interpretation of Failure to Reject

Non-inferiorityを示せなかった場合、

> TargetingがSend Allより劣ると証明された

とは限らない。

以下を区別する。

### Clear Inferiority

Effect estimateとconfidence intervalがnon-inferiority marginより明確に悪い。

### Inconclusive

Confidence intervalが広く、non-inferiority boundaryを跨ぐ。

後者の場合は、

> Evidence insufficient

と判断する。

---

## 28. Experiment Stop Rules

通常の固定sample designを基本とする。

途中結果を繰り返し確認し、有意になった時点で停止する運用は行わない。

Sequential designを使用する場合は、

* Interim timing
* Alpha spending
* Stop boundary
* Futility rule

をexperiment開始前に定義する。

本設計書のdefaultでは固定sample designとする。

---

## 29. Pre-registration Checklist

Experiment開始前に以下を確定する。

* [ ] Eligible population
* [ ] Randomization unit
* [ ] Arm allocation
* [ ] Frozen uplift model
* [ ] Model version
* [ ] Feature definitions
* [ ] Top-10% targeting rule
* [ ] Tie handling
* [ ] Primary outcome
* [ ] Outcome measurement window
* [ ] Primary estimand
* [ ] NI margin
* [ ] Alpha
* [ ] Power
* [ ] Required sample size
* [ ] Covariate adjustment specification
* [ ] Missing-data handling
* [ ] Secondary outcomes
* [ ] Multiple-testing rule
* [ ] Business net-value equation
* [ ] Gross margin assumption
* [ ] Delivery cost
* [ ] Final decision threshold

すべてをOutcome観測前に確定する。

---

## 30. Current Recommendation

現時点では、

> Women's EmailのSend Allをproduction baselineとして維持する。

Top-10% targetingは、

> promising but unvalidated policy

として扱う。

本番置換は行わず、business-justified non-inferiority marginと実行可能なsample sizeを確定できた場合のみprospective RCTへ進む。

---

## 31. Experiment Summary

### Control Policy

Send All

### Candidate Policy

Frozen Women's Email Top-10% Uplift Targeting

### Primary Outcome

Spend per randomized user

### Primary Estimand

$$
E[Spend\mid Targeting]
-
E[Spend\mid SendAll]
$$

### Primary Framework

Non-inferiority

### Randomization

1:1 user-level randomization

### Targeting Rate

約10%

### Primary Statistical Principle

Intent-to-Treat

### Model Rule

実験開始前に完全freeze

### Final Decision

Statistical non-inferiorityだけではなく、

$$
Statistical\ Evidence
+
Delivery\ Cost
+
Gross\ Margin
+
Operational\ Feasibility
$$

を統合して判断する。
