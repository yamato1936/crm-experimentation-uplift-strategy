# CRM配信戦略 Decision Memo

## 1. 結論

現時点では、**Men's Email / Women's Email ともにSend Allをベースライン施策として維持する**のが妥当です。

ただしWomen's Emailについては、事前購買履歴による効果の異質性とuplift rankingのシグナルが確認されているため、**将来的なtargeting配信の候補**とします。

一方、現在のデータだけではTop-10% targetingがSend Allを上回るとは結論できません。したがって、Women's Email targetingは本番導入せず、model・対象割合・判定ルールを固定したうえで次回のrandomized experimentで検証します。

## 2. Business Question

> CRMキャンペーンは本当にユーザー行動を改善したのか。全員に配信すべきか。それとも効果のあるユーザーだけに配信すべきか？

意思決定は次の3段階で行いました。

1. Email配信そのものに平均的な因果効果があるか
2. 効果がユーザー属性によって異なるか
3. Uplift modelを用いたtargetingがSend Allより有利か

## 3. データと実験の妥当性

Hillstrom Email Marketing Datasetの64,000ユーザーを分析対象としました。

Treatment:

- Control: No E-Mail
- Men's Email
- Women's Email

### Sample Ratio Mismatch

```text
Chi-square = 0.203
p-value    = 0.904
SRM flag   = False
```

Treatment allocationに明確な異常は確認されませんでした。

### Pre-treatment balance

主要pre-treatment covariatesのpairwise SMDを確認した結果、最大absolute SMDは約0.017でした。`|SMD| >= 0.10`となる変数はありませんでした。

したがって、**Sample Ratio Mismatchまたは重大なpre-treatment covariate imbalanceを示す証拠は確認されなかった**と判断しました。

これはrandomizationが証明されたことを意味せず、観測可能な診断上、大きな問題が検出されなかったことを意味します。

## 4. Average Treatment Effect

Intent-to-TreatとしてControlに対する各Email施策の平均処置効果を推定しました。

### Men's Email vs Control

| Outcome | Control | Men's Email | ATE |
| --- | ---: | ---: | ---: |
| Visit Rate | 10.62% | 18.28% | +7.66pp |
| Conversion Rate | 0.57% | 1.25% | +0.68pp |
| Spend / User | 0.653 | 1.423 | +0.770 |

3指標すべてで正の効果が確認され、Holm補正後も統計的に有意でした。

### Women's Email vs Control

| Outcome | Control | Women's Email | ATE |
| --- | ---: | ---: | ---: |
| Visit Rate | 10.62% | 15.14% | +4.52pp |
| Conversion Rate | 0.57% | 0.88% | +0.31pp |
| Spend / User | 0.653 | 1.077 | +0.424 |

こちらも3指標すべてで正の効果が確認され、Holm補正後も統計的に有意でした。

平均効果だけを見る限り、**Emailを送らないより、Men's Email / Women's Emailを送った方がユーザー行動は改善する**という結論を支持します。

なお、Men's Emailの点推定値はWomen's Emailより大きいですが、両施策を直接比較する検定は行っていないため、「Men's Emailの方が統計的に優れている」とは結論していません。

## 5. Treatment Effect Heterogeneity

Descriptive subgroup review後に選択したinteractionをtargeted follow-up analysisとして評価しました。

### Women's Email x prior womens purchase

Visit:

```text
Interaction effect      = +6.20pp
95% CI                  = [4.95pp, 7.46pp]
Holm-adjusted p-value   < 0.001

womens = 0: +1.11pp
womens = 1: +7.31pp
```

Conversion:

```text
Interaction effect      = +0.45pp
95% CI                  = [0.13pp, 0.77pp]
Holm-adjusted p-value   = 0.028

womens = 0: +0.06pp
womens = 1: +0.51pp
```

Spendについてinteractionの統計的証拠は十分ではありませんでした。

### Men's Email x prior mens purchase

Visit、Conversion、Spendのいずれについても十分なinteraction evidenceは確認されませんでした。

Women's Emailでは、**過去にWomen's merchandiseを購入したユーザーほど、Visit / Conversionへの効果が大きい可能性がある**というシグナルが得られました。

ただし、この仮説はdescriptive subgroup review後に選択されたため、探索的結果として扱います。

## 6. Uplift Modeling

Pre-treatment featuresのみを使ったT-Learnerを構築し、Men's Email vs Control、Women's Email vs Controlを別々のbinary treatment problemとして学習しました。

### Men's Email

```text
Conversion Qini = -0.00023
Spend Qini      = +0.00430
```

Targetingによって明確に高upliftユーザーを識別できているとは言いにくい結果です。

### Women's Email

```text
Conversion Qini = +0.00067
Spend Qini      = +0.03670
```

Top 20% Conversion:

```text
Observed uplift = +1.05pp
95% CI          = [0.23pp, 1.88pp]
```

Top 10% Spend:

```text
Observed uplift = +2.486 / user
95% CI          = [0.428, 4.544]
```

Women's Emailでは、Men's Emailより明確なuplift ranking signalが確認されました。

ただしTop-10%は結果確認後に有望と判断した割合であり、独立したvalidation sampleで確証されたpolicyではありません。

## 7. Policy Evaluation

Held-out predictionsを用いて以下のpolicyを比較しました。

- Send None
- Send All
- Top 10%
- Top 20%
- Top 30%
- Top 50%

Policy valueはInverse Propensity Weightingで推定しました。

### Men's Email x Spend

| Policy | Policy Value | vs Send All |
| --- | ---: | ---: |
| Send All | 1.581 | 0.000 |
| Top 10% | 0.826 | -0.755 |
| Top 20% | 0.893 | -0.688 |
| Top 30% | 0.946 | -0.635 |
| Top 50% | 1.213 | -0.367 |

すべてのTop-k policyでSend Allよりgross spendが低く、その差の95% CIも0を跨ぎませんでした。

したがってMen's Emailでは、**Targetingによってgross spendを維持しながら配信量を減らせる証拠はない**と判断します。

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
Point estimate = -0.301
95% CI         = [-0.745, +0.114]
```

したがって、Women's Email Top-10% targetingがSend Allと同等以上のgross spendを維持するとは現時点では結論できません。

一方でCIは0を跨いでおり、Send Allに対するgross spend lossの大きさ自体にも不確実性があります。

## 8. Delivery Costを考慮した意思決定

Hillstrom Datasetには実際のメール配信コスト、粗利率、利益率がありません。

そのため架空のコストを仮定せず、Spendと同じ単位でbreak-even delivery costを計算しました。

Women's Email Top-10%のSend Allに対するpoint-estimate break-even thresholdは約0.334です。

```text
If delivery cost > 0.334 revenue-units / email,
Top-10% targeting may outperform Send All in estimated net value.
```

ただしこれはprofit thresholdではありません。

実務では次のようにgross marginを含めて判断すべきです。

```text
Net Value = Gross Margin * Incremental Spend - Delivery Cost
```

したがって0.334は**revenue-equivalent break-even threshold**としてのみ解釈します。

## 9. 次回実験

Women's Email targetingを本番導入する前にprospective RCTを実施します。

- **Arm A:** Send All
- **Arm B:** Frozen Top-10% Targeting Policy

Primary estimand:

```text
Delta = E[Spend | Targeting] - E[Spend | Send All]
```

配信量を約90%削減する代わりに一定のSpend低下を許容する意思決定であるため、non-inferiority designを主要候補とします。

```text
H0: Delta <= -Margin
H1: Delta >  -Margin
```

Marginは必要sample sizeを小さくするために選ぶのではなく、gross margin、delivery cost、opportunity cost、business toleranceから事前に決定します。

## 10. Power / Feasibility

Planning SDは約16.76です。

真のdifferenceを0と仮定した場合:

| NI Margin | Required N / Arm | Total N |
| ---: | ---: | ---: |
| 0.10 | 347,149 | 694,298 |
| 0.20 | 86,788 | 173,576 |
| 0.30 | 38,573 | 77,146 |
| 0.40 | 21,697 | 43,394 |
| 0.50 | 13,886 | 27,772 |

Historical point estimate `Delta = -0.300664` が再現すると仮定した場合:

| NI Margin | Feasibility |
| ---: | ---: |
| 0.10 | 達成不可 |
| 0.20 | 達成不可 |
| 0.30 | 達成不可 |
| 0.40 | Total N 約703,610 |
| 0.50 | Total N 約174,734 |

現在観測されたeffectが再現する場合、小さいnon-inferiority marginでtargetingを実証することは難しいと分かります。

## 11. 最終Decision

### Men's Email

**Decision: Send Allを維持**

理由:

- Controlに対する平均処置効果は明確に正
- 強いtreatment heterogeneityの証拠なし
- Uplift ranking performanceは弱い
- Top-k targetingはSend Allよりgross spendを有意に低下させた

### Women's Email

**Decision: Send Allを現行ベースラインとして維持し、Targetingは検証候補とする**

理由:

- Controlに対する平均処置効果は正
- Prior womens purchaseによるVisit / Conversion heterogeneityのsignalあり
- Uplift modelでpositive ranking signalあり
- 一部Top-kで高いincremental effectが観測された
- しかしSend Allとのgross spend差は不確実
- Targeting policyはprospective validationされていない
- 経済的に妥当なnon-inferiority marginを決めるための粗利・配信コスト情報が不足

したがって、**Women's Email targetingは有望だが、現在の証拠だけでSend Allを置き換えるべきではない**と判断します。
