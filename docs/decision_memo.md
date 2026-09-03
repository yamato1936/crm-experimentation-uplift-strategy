# CRM配信戦略 Decision Memo

## 1. 結論

現時点では、**Men's Email / Women's Email ともに一律配信をベースライン施策として維持する**のが妥当である。

一方で、Women's Email については、事前購買履歴による効果の異質性と uplift ranking のシグナルが確認されており、**将来的なターゲティング配信の候補**とする価値がある。

ただし、現在のデータだけでは Top-10% targeting が Send All を上回るとは結論できない。したがって、Women's Email の targeting は本番導入せず、モデル・対象割合・判定ルールを固定したうえで、次回のランダム化比較試験で検証する。

---

## 2. Business Question

本分析では、以下の問いに答えることを目的とした。

> CRMキャンペーンは本当にユーザー行動を改善したのか。全員に配信すべきか。それとも効果のあるユーザーだけに配信すべきか？

意思決定は以下の3段階で行った。

1. Email配信そのものに平均的な因果効果があるか
2. 効果がユーザー属性によって異なるか
3. Uplift modelを用いたtargetingがSend Allより有利か

---

## 3. データと実験の妥当性

Hillstrom Email Marketing Dataset の64,000ユーザーを分析対象とした。

実験群は以下の3群である。

* Control: No E-Mail
* Men's Email
* Women's Email

ランダム化の妥当性について、Sample Ratio Mismatch と事前共変量バランスを確認した。

### SRM

* Chi-square: 0.203
* p-value: 0.904
* SRM flag: False

Treatment allocationに明確な異常は確認されなかった。

### Pre-treatment balance

主要な事前共変量についてpairwise SMDを確認した結果、最大でも約0.017であり、一般的な基準である `|SMD| >= 0.10` に達する変数はなかった。

したがって、

> Sample Ratio Mismatchまたは重大な事前共変量の不均衡を示す証拠は確認されなかった。

と判断した。

これはランダム化が「証明された」ことを意味するものではなく、観測可能な診断上、大きな問題が検出されなかったことを意味する。

---

## 4. 平均処置効果

ITTとして、Controlに対する各Email施策の平均処置効果を推定した。

### Men's Email vs Control

| Outcome         | Control | Men's Email |     ATE |
| --------------- | ------: | ----------: | ------: |
| Visit Rate      |  10.62% |      18.28% | +7.66pp |
| Conversion Rate |   0.57% |       1.25% | +0.68pp |
| Spend / User    |   0.653 |       1.423 |  +0.770 |

3指標すべてで正の効果が確認され、Holm補正後も統計的に有意であった。

### Women's Email vs Control

| Outcome         | Control | Women's Email |     ATE |
| --------------- | ------: | ------------: | ------: |
| Visit Rate      |  10.62% |        15.14% | +4.52pp |
| Conversion Rate |   0.57% |         0.88% | +0.31pp |
| Spend / User    |   0.653 |         1.077 |  +0.424 |

Women's Emailも3指標すべてで正の効果が確認され、Holm補正後も統計的に有意であった。

### 判断

平均効果だけを見る限り、

> Emailを送らないより、Men's Email / Women's Emailを送った方がユーザー行動は改善する。

という結論を支持する。

なお、Men's Emailの点推定値はWomen's Emailより大きいが、Men's EmailとWomen's Emailを直接比較する検定は行っていないため、「Men's Emailの方が統計的に優れている」とは結論していない。

---

## 5. Treatment Effect Heterogeneity

事前共変量による効果の異質性を探索した。

descriptive subgroup review後に選択したinteractionであるため、これらはconfirmatory analysisではなく、**targeted follow-up analysis**として扱う。

### Women's Email × prior womens purchase

Women's Emailでは、`womens`によるinteractionが一部outcomeで確認された。

#### Visit

* Interaction effect: +6.20pp
* 95% CI: [4.95pp, 7.46pp]
* Holm-adjusted p-value: < 0.001

Stratum-specific effect:

* `womens = 0`: +1.11pp
* `womens = 1`: +7.31pp

#### Conversion

* Interaction effect: +0.45pp
* 95% CI: [0.13pp, 0.77pp]
* Holm-adjusted p-value: 0.028

Stratum-specific effect:

* `womens = 0`: +0.06pp
* `womens = 1`: +0.51pp

#### Spend

Spendについてinteractionの統計的証拠は十分ではなかった。

### Men's Email × prior mens purchase

Visit、Conversion、Spendのいずれについても、十分なinteraction evidenceは確認されなかった。

### 判断

Women's Emailでは、

> 過去にWomen's merchandiseを購入したユーザーほど、Visit / Conversionへの効果が大きい可能性がある。

というシグナルが得られた。

ただし、この仮説はdescriptive subgroup review後に選択されたため、探索的結果として扱う。

---

## 6. Uplift Modeling

次に、平均効果ではなく、

> 誰に送るとincremental effectが大きいか

を推定するため、pre-treatment featuresのみを用いたT-Learnerを構築した。

Men's Email vs Control、Women's Email vs Controlを別々のbinary treatment problemとして学習し、held-out dataで評価した。

### Men's Email

#### Conversion

* Qini: -0.00023

#### Spend

* Qini: +0.00430

Targetingによって明確に高upliftユーザーを識別できているとは言いにくい。

### Women's Email

#### Conversion

* Qini: +0.00067

Top 20%:

* Observed uplift: +1.05pp
* 95% CI: [0.23pp, 1.88pp]

#### Spend

* Qini: +0.03670

Top 10%:

* Observed uplift: +2.486 / user
* 95% CI: [0.428, 4.544]

Women's Emailでは、Men's Emailよりも明確なuplift ranking signalが確認された。

ただし、Top-10%という割合は結果を確認した後に有望と判断したものであり、独立したvalidation sampleで確証されたpolicyではない。

---

## 7. Policy Evaluation

held-out predictionsを用いて、以下のpolicyを比較した。

* Send None
* Send All
* Top 10%
* Top 20%
* Top 30%
* Top 50%

policy valueはInverse Propensity Weightingを用いて推定した。

### Men's Email × Spend

| Policy   | Policy Value | vs Send All |
| -------- | -----------: | ----------: |
| Send All |        1.581 |       0.000 |
| Top 10%  |        0.826 |      -0.755 |
| Top 20%  |        0.893 |      -0.688 |
| Top 30%  |        0.946 |      -0.635 |
| Top 50%  |        1.213 |      -0.367 |

すべてのTop-k policyでSend Allよりgross spendが低く、その差の95% CIも0を跨がなかった。

したがって、Men's Emailでは現状、

> Targetingによってgross spendを維持しながら配信量を減らせる証拠はない。

### Women's Email × Spend

| Policy   | Policy Value | vs Send All |
| -------- | -----------: | ----------: |
| Send All |        1.156 |       0.000 |
| Top 10%  |        0.855 |      -0.301 |
| Top 20%  |        0.838 |      -0.317 |
| Top 30%  |        0.868 |      -0.287 |
| Top 50%  |        0.895 |      -0.261 |

Top-10%のSend Allとの差は、

* Point estimate: -0.301
* 95% CI: [-0.745, +0.114]

であった。

したがって、

> Women's Email Top-10% targetingがSend Allと同等以上のgross spendを維持する

とは現時点では結論できない。

一方で、CIは0を跨いでおり、Send Allに対するgross spend lossの大きさ自体にも不確実性がある。

---

## 8. Delivery Costを考慮した意思決定

Hillstrom Datasetには実際のメール配信コスト、粗利率、利益率が存在しない。

そのため、架空のコストを仮定するのではなく、Spendと同じ単位でbreak-even delivery costを計算した。

Women's Email Top-10%では、Send Allに対するbreak-even point estimateは、

$$
c^* \approx 0.334
$$

であった。

つまり、Spendをそのまま経済価値として扱う単純化のもとでは、1配信あたりのコストが約0.334を超える場合、Top-10% targetingの方がSend Allより高いnet valueを持つ可能性がある。

ただし、これはprofit thresholdではない。

実務では、

$$
NetValue
=
GrossMargin \times IncrementalSpend
-
DeliveryCost
$$

で評価すべきであり、粗利率が不明なため最終的な経済判断はできない。

したがって、0.334は**revenue-equivalent break-even threshold**としてのみ解釈する。

---

## 9. 次回実験の設計

Women's Email targetingを本番導入する前に、prospective RCTを実施する。

### Arm A

**Send All**

Women's Emailを全eligible userに配信する。

### Arm B

**Frozen Top-10% Targeting Policy**

現在構築したuplift model、features、model parameters、targeting thresholdを事前に固定し、uplift score上位約10%のみにWomen's Emailを配信する。

experiment開始後にモデルやthresholdを変更しない。

### Primary Estimand

$$
\Delta
=
E[Spend \mid Targeting]
-
E[Spend \mid SendAll]
$$

### 推奨する検定

配信量を90%削減する代わりに一定のSpend低下を許容する意思決定であるため、単純なsuperiority testよりもnon-inferiority designが適している。

$$
H_0:\Delta \le -M
$$

$$
H_1:\Delta > -M
$$

ここで \(M\) は、事業上許容可能なSpend/userの最大低下量である。

---

## 10. Power / Feasibility

Spendは非常にzero-inflatedかつ高分散であり、held-out dataではplanning SDが約16.76であった。

真の差を0と仮定した場合、80% power・片側alpha 5%のnon-inferiority designでは、

| NI Margin | 必要N / Arm | Total N |
| --------: | --------: | ------: |
|      0.10 |   347,149 | 694,298 |
|      0.20 |    86,788 | 173,576 |
|      0.30 |    38,573 |  77,146 |
|      0.40 |    21,697 |  43,394 |
|      0.50 |    13,886 |  27,772 |

さらに、今回観測された、

$$
\Delta=-0.300664
$$

が真の差に近いと仮定すると、

* Margin 0.10: non-inferiority達成不可
* Margin 0.20: non-inferiority達成不可
* Margin 0.30: non-inferiority達成不可
* Margin 0.40: Total N 約703,610
* Margin 0.50: Total N 約174,734

となる。

つまり現在観測されたeffectが再現する場合、小さいnon-inferiority marginでtargetingを実証することは難しい。

Marginは必要sample sizeを小さくするために選ぶのではなく、粗利・配信コスト・機会費用などのbusiness toleranceから事前に決定する必要がある。

---

## 11. 最終Decision

### Men's Email

**Decision: Send Allを維持**

理由:

* Controlに対する平均処置効果は明確に正
* 強いtreatment heterogeneityの証拠なし
* Uplift ranking performanceは弱い
* Top-k targetingはSend Allよりgross spendを有意に低下させた

現時点では、targeting modelを利用する根拠は弱い。

### Women's Email

**Decision: Send Allを現行ベースラインとして維持し、Targetingは検証候補とする**

理由:

* Controlに対する平均処置効果は正
* Prior womens purchaseによるVisit / Conversion heterogeneityのsignalあり
* Uplift modelでpositive ranking signalあり
* 一部Top-kで高いincremental effectが観測された
* しかしSend Allとのgross spend差は不確実
* Targeting policyはprospective validationされていない
* 経済的に妥当なnon-inferiority marginを決めるための粗利・配信コスト情報が不足

したがって、

> Women's Email targetingは有望だが、現在の証拠だけでSend Allを置き換えるべきではない。

---

## 12. 推奨アクション

1. Men's EmailはSend Allを維持する。
2. Women's Emailも現時点ではSend Allを維持する。
3. Women's Top-10% targetingを次回検証候補としてfreezeする。
4. 実務上の粗利率・1配信あたりコストを取得する。
5. それらからbusiness-justified non-inferiority marginを事前設定する。
6. 必要sample sizeと実験期間が現実的か評価する。
7. 実行可能であれば、Send All vs Frozen Top-10% Policyのprospective RCTを実施する。

---

## 13. 意思決定サマリー

**平均効果:** Email施策は有効。

**異質性:** Women's Emailでは一部ユーザーで効果が大きい可能性がある。

**Uplift:** Women's Emailにはtargeting signalがある。

**Policy Value:** 現在のtargetingはSend Allを確実に上回っていない。

**Economics:** 粗利率と配信コスト不足のため最適policyは確定できない。

**Final Decision:** Send Allを維持し、Women's targetingを次回RCTで検証する。
