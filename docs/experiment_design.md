# 次回ランダム化比較試験の設計

## 1. 目的

本ドキュメントでは、既存分析から得られたWomen's Emailのターゲティング仮説を、新しいランダム化比較試験で前向きに検証するための設計を定義します。

既存分析ではWomen's Emailについて、以下が確認されています。

- 対照群に対する正の平均処置効果
- 一部の事前共変量による処置効果の異質性
- アップリフトモデルによる順位付けシグナル
- Top-k targetingによる配信効率改善の可能性

一方で、Top-k targetingが一律配信より高いgross spendを生み出すことは確認できていません。

したがって次回実験では、

> Women's Emailをeligible user全員に送る現行方針と比較して、事前に固定したuplift targeting policyが、許容可能なSpend lossの範囲内で配信量を削減できるか

を検証します。

---

## 2. 主要なビジネス上の問い

> Women's Emailをeligible user全員に送る代わりに、事前に固定したuplift modelによって上位10%のユーザーだけに送ることで、Spend per randomized userを事業上許容可能な範囲に維持しながら、配信量を削減できるか？

本実験の主目的は、targeting policyがSend Allより「有意に高いSpend」を生むことを証明することではありません。

配信量を約90%削減するpolicyであるため、一定のSpend lossを許容した上での**non-inferiority**を主要な意思決定フレームとします。

---

## 3. 実験群

### Arm A: 一律配信

eligible user全員にWomen's Emailを配信します。

$$
\pi_A(x)=1
$$

### Arm B: 固定済みTop-10%ターゲティング

既存データで学習済みのuplift modelを用いてuplift scoreを計算し、事前に固定したルールに基づいて上位約10%のユーザーのみにWomen's Emailを配信します。

$$
\pi_B(x)
=
\begin{cases}
1 & \hat\tau(x)\ge c \\
0 & \hat\tau(x)<c
\end{cases}
$$

ここで、

- $\hat\tau(x)$: frozen uplift modelによるpredicted uplift
- $c$: 実験開始前に固定したTop-10% threshold

です。

Arm B内でTop-10%に入らなかったユーザーにはEmailを配信しません。

---

## 4. ランダム化単位

Randomization unitはeligible userとします。

同一ユーザーが複数armに入らないよう、ユーザー単位でArm A / Arm Bへ割り付けます。

推奨allocation ratioは

$$
1:1
$$

です。

---

## 5. 適格条件

実験対象者は、少なくとも以下を満たすユーザーとします。

- Women's Email campaignの配信対象としてbusiness上eligible
- uplift scoringに必要なpre-treatment featureが利用可能
- Experiment開始前にTreatment assignment可能
- Outcome measurement期間を定義可能

既存分析と同様、model featureにはpre-treatment variableのみを使用します。

---

## 6. 配信方針の固定

本実験の最重要ルールは、

> Outcomeを見る前にtargeting policyを完全に固定する

ことです。

以下をexperiment開始前にfreezeします。

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

既存分析で使用したWomen's Email vs ControlのT-Learner。

### Treatment Definition

- Treatment: Women's Email
- Control action within targeting policy: No Email

### Scoring Logic

$$
\hat\tau(x)
=
\hat\mu_1(x)-\hat\mu_0(x)
$$

を変更しません。

### Target Fraction

$$
10\%
$$

に固定します。

### Threshold

実験対象populationに対するuplift score rankingからTop-10%を決定する具体的なルールを事前に固定します。

tieが発生する場合の処理方法も事前に定義します。

---

## 7. 方針選択に関する注意

Top-10% policyは、既存held-out analysisで有望なsignalが観測された後に選択されました。

したがって、既存分析におけるTop-10%の成績は**exploratory evidence**です。

一方、新しい独立したRCTを開始する前にpolicyをfreezeすれば、次回実験ではそのpolicyをprospectiveに検証できます。

実験開始後に以下を行ってはいけません。

- Top-20%へ変更する
- 別モデルへ変更する
- Featureを追加する
- Thresholdを変更する
- Outcomeを見ながらmodelを再学習する

---

## 8. 主要アウトカム

Primary OutcomeはSpend per randomized userとします。

各ユーザーについて実験期間中のSpendを測定し、conversionの有無にかかわらず全randomized userを分析対象に含めます。

$$
Y_i=Spend_i
$$

conversionしたユーザーだけに限定しません。

---

## 9. 主要な推定対象

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

とします。

これはpolicy-level Intent-to-Treat estimandです。

Arm Bで実際にEmailを受け取るユーザーが約10%だけであっても、Arm Bへrandomizeされた全ユーザーを分母に含めます。

---

## 10. 主要仮説

Non-inferiority marginを

$$
M>0
$$

とします。

Hypothesisは、

$$
H_0:\Delta\le-M
$$

$$
H_1:\Delta>-M
$$

です。

つまり、

> TargetingによるSpend lossが、事前に定めた最大許容loss $M$ より小さいか

を検証します。

---

## 11. 非劣性マージン

$M$ は統計的に都合の良い値ではなく、**business toleranceから決める**必要があります。

既存分析では以下のmarginについてsample-size sensitivityを確認しました。

| NI Margin | True Difference = 0を仮定したTotal N |
| ---: | ---: |
| 0.10 | 694,298 |
| 0.20 | 173,576 |
| 0.30 | 77,146 |
| 0.40 | 43,394 |
| 0.50 | 27,772 |

必要Nが小さいという理由だけでmarginを大きくしてはいけません。

margin決定には少なくとも以下が必要です。

- Gross margin
- Email delivery cost
- Campaign operational cost
- Customer contact cost
- Opportunity cost
- Business risk tolerance

---

## 12. 経済的な意思決定ルール

Spendは売上に近い指標であり、Profitではありません。

実務上は、

$$
\mathrm{NetValue}
=
\mathrm{GrossMargin}\times Spend
-\mathrm{DeliveryCost}
$$

を評価すべきです。

Send AllとTargetingのnet value差は、

$$
\Delta NetValue
=
m\Delta Spend
+c(1-r)
$$

と表せます。

ここで、

- $m$: Gross margin
- $c$: 1通あたりdelivery cost
- $r$: Targeting policyの配信率

です。

Top-10% policyでは

$$
r\approx0.10
$$

なので、約90%の配信削減効果があります。

したがって、一定のSpend lossが存在しても、delivery cost savingによってnet valueではTargetingが優位になる可能性があります。

---

## 13. 既存分析から得られた参考値

既存held-out analysisにおけるWomen's Email Top-10% policyの結果は以下でした。

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

このCIは0をまたいでいるため、Top-10%がSend Allと同等であるとも、Send Allより劣るとも確定できません。

この結果は次回実験を設計するためのhistorical contextとして使用しますが、prospective hypothesis testの結果として再利用しません。

---

## 14. 既存分析の損益分岐点

既存policy evaluationでは、Top-10% targetingとSend Allのbreak-even delivery cost point estimateは

$$
c^*\approx0.334
$$

でした。

これは、Spendをそのまま経済価値として扱った場合、1配信あたり約0.334以上のコストが存在すると、Top-10% policyがSend Allよりnet valueで有利になる可能性があることを意味します。

ただしgross marginが不明なため、これはprofit thresholdではありません。

本実験の正式なbusiness decision ruleには、実際のmargin / delivery costを使用します。

---

## 15. 副次アウトカム

Primary hypothesisを変更しない範囲で、以下をsecondary outcomeとして確認します。

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

を計算できます。

ただし、これはprimary causal estimandではありません。

---

## 16. 主要解析

Primary analysisはIntent-to-Treatで実施します。

Arm assignmentに基づき、

$$
\hat\Delta
=
\bar Y_B-\bar Y_A
$$

を推定します。

Primary conclusionは、$\hat\Delta$ のone-sided confidence boundと事前定義したnon-inferiority margin $M$ の関係で判断します。

Non-inferiorityが成立するには、confidence intervalの下限が

$$
-M
$$

を上回る必要があります。

---

## 17. 分散推定

Spendはzero-inflatedかつheavy-tailedです。

そのため、normal approximationだけに依存せず、

- Welch-type robust inference
- Heteroskedasticity-robust standard error
- Bootstrap confidence interval

などによるrobustness checkを行います。

Primary analysis methodはexperiment開始前に固定します。

---

## 18. 共変量調整

Randomizationによってunadjusted ITT estimatorは因果推論上妥当です。

一方、Spendの分散が大きいため、precision improvementを目的としてpre-treatment covariatesによるadjustmentを検討します。

基本形は、

$$
Y_i
=
\alpha
+\tau Z_i
+\beta^\top X_i
+\epsilon_i
$$

です。

ここで、

- $Z_i$: Arm B indicator
- $X_i$: pre-treatment covariates
- $\tau$: adjusted policy effect

です。

Covariatesはexperiment開始前に固定し、Outcomeを見た後に「効いた変数だけ」を選択しません。

---

## 19. サンプルサイズ設計

既存held-out dataでは、

- Women's Email SD: 約16.76
- Control SD: 約10.25

でした。

保守的なplanning valueとして、

$$
\sigma_{plan}=16.76
$$

を使用しました。

### Two-sided MDE Sensitivity

| Spend/User MDE | Total N |
| ---: | ---: |
| 0.10 | 881,424 |
| 0.20 | 220,356 |
| 0.30 | 97,936 |
| 0.40 | 55,090 |
| 0.50 | 35,258 |

### Non-inferiority Sensitivity

True differenceを0と仮定した場合:

| NI Margin | Total N |
| ---: | ---: |
| 0.10 | 694,298 |
| 0.20 | 173,576 |
| 0.30 | 77,146 |
| 0.40 | 43,394 |
| 0.50 | 27,772 |

---

## 20. Historical Effectを仮定したSensitivity

既存held-out estimate、

$$
\Delta=-0.300664
$$

が真の効果に近いと仮定すると、

| NI Margin | Feasibility |
| ---: | ---: |
| 0.10 | 達成不可 |
| 0.20 | 達成不可 |
| 0.30 | 達成不可 |
| 0.40 | Total N 約703,610 |
| 0.50 | Total N 約174,734 |

となります。

これは、現在のpoint estimateが再現する場合、小さいmarginでnon-inferiorityを証明することが困難であることを示します。

ただし、このhistorical estimateを次回experimentの真のeffectとして固定しません。

---

## 21. Randomization Checks

Experiment開始後、outcome分析前に以下を確認します。

### Sample Ratio Mismatch

Arm A / Arm Bのallocationが設計通りであるか確認します。

### Pre-treatment Balance

主要covariateについてSMDを確認します。

ただしbalance testの結果を見てexperiment sampleを恣意的に変更しません。

### Treatment Delivery

- Send All armで予定通り配信されたか
- Targeting armでTop-10%ルールが正しく適用されたか

を確認します。

---

## 22. 実装忠実度

Targeting policyの実験では、統計的randomizationだけでなくpolicy implementationの正確性が重要です。

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

これにより、Randomizationは正しかったがproduction logicが違っていた、という問題を切り分けられるようにします。

---

## 23. 欠測データ

Randomization後のmissing outcomeが発生した場合、missingnessをTreatment assignment別に確認します。

Outcome missingnessがTreatmentによって異なる場合、単純なcomplete-case analysisにはbiasの可能性があります。

Missing-data handling ruleはexperiment開始前に定義します。

可能な限り、randomized user全員についてSpendを0を含めて観測可能な設計とします。

---

## 24. 多重検定

### Primary Test

Primary testは、

> Women's Frozen Top-10% Targeting vs Send AllのSpend non-inferiority

の1つとします。

このprimary hypothesisについてalphaを確保します。

### Secondary Outcomes

Visit / Conversion等のsecondary outcomeはprimary decisionと分離します。

複数secondary hypothesisについてformal significance claimsを行う場合はHolm等のmultiple-testing correctionを適用します。

---

## 25. 意思決定基準

### Targetingを採用できる条件

最低限、以下を満たす必要があります。

1. Primary non-inferiority criterionを満たす
2. Frozen policyがproduction上正しく実装されている
3. 配信削減量が想定通りである
4. Gross margin / delivery costを含めたnet valueがSend All以上
5. Safety / customer experience上の重大な悪化がない

### Send Allを維持する条件

以下のいずれかの場合、一律配信を維持します。

- Non-inferiorityを示せない
- Net valueがSend Allを下回る
- Targeting implementationが不安定
- Experiment powerが不足して結論不能

### Send None

Women's Email自体がControlより正のATEを持つ既存証拠があるため、現在の主要候補ではありません。

ただし将来的にdelivery costやbusiness constraintが大きく変化する場合は再評価します。

---

## 26. 棄却できなかった場合の解釈

Non-inferiorityを示せなかった場合、TargetingがSend Allより劣ると証明されたとは限りません。

以下を区別します。

### Clear Inferiority

Effect estimateとconfidence intervalがnon-inferiority marginより明確に悪い。

### Inconclusive

Confidence intervalが広く、non-inferiority boundaryをまたぐ。

後者の場合は、**Evidence insufficient**と判断します。

---

## 27. 実験停止ルール

通常の固定sample designを基本とします。

途中結果を繰り返し確認し、有意になった時点で停止する運用は行いません。

Sequential designを使用する場合は、

- Interim timing
- Alpha spending
- Stop boundary
- Futility rule

をexperiment開始前に定義します。

本設計書のdefaultでは固定sample designとします。

---

## 28. 事前登録チェックリスト

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

すべてをOutcome観測前に確定します。

---

## 29. 現時点の推奨方針

現時点では、Women's Emailの一律配信をproduction baselineとして維持します。

Top-10% targetingは、**promising but unvalidated policy**として扱います。

本番置換は行わず、business-justified non-inferiority marginと実行可能なsample sizeを確定できた場合のみprospective RCTへ進みます。

---

## 30. 実験設計サマリー

- Control Policy: Send All
- Candidate Policy: Frozen Women's Email Top-10% Uplift Targeting
- Primary Outcome: Spend per randomized user
- Primary Estimand: $E[Spend\mid Targeting]-E[Spend\mid SendAll]$
- Primary Framework: Non-inferiority
- Randomization: 1:1 user-level randomization
- Targeting Rate: 約10%
- Primary Statistical Principle: Intent-to-Treat
- Model Rule: 実験開始前に完全freeze

最終意思決定は、

$$
Statistical\ Evidence
+
Delivery\ Cost
+
Gross\ Margin
+
Operational\ Feasibility
$$

を統合して判断します。
