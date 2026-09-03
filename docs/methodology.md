# 分析方法

## 1. 分析目的

本プロジェクトでは、Hillstrom Email Marketing Datasetを用いて、CRMキャンペーンの因果効果とターゲティング配信の意思決定価値を評価します。

中心となる問いは以下です。

> CRMキャンペーンは本当にユーザー行動を改善したのか。全員に配信すべきか。それとも効果の高いユーザーだけに配信すべきか？

分析は次の順序で進めました。

1. データ品質監査
2. ランダム化診断
3. 分析母集団の構築
4. A/B指標の集計
5. 平均処置効果の推定
6. 処置効果の異質性分析
7. アップリフト・モデリング
8. 配信方針の価値評価
9. 次回実験設計
10. 検出力・実行可能性分析

目的は予測精度の高いモデルを作ることではなく、**因果推論から配信方針の意思決定まで一貫した分析フローを構築すること**です。

---

## 2. データ

### 2.1 データセット

使用データはHillstrom Email Marketing Datasetです。

観測単位はユーザーで、総行数は64,000です。

処置群は以下の3群です。

- `No E-Mail`
- `Mens E-Mail`
- `Womens E-Mail`

分析時には以下へ正規化しました。

- `control`
- `mens_email`
- `womens_email`

### 2.2 アウトカム

主要アウトカムは以下の3つです。

- `visit`
- `conversion`
- `spend`

`visit` と `conversion` は二値アウトカム、`spend` は連続値として扱います。

Spendはconversionしたユーザーだけに限定せず、**ランダム化された全ユーザーを分母としたSpend per randomized user**として評価します。

conversionは処置後変数であるため、

$$
E[Spend\mid Conversion=1]
$$

のような条件付き分析を行うと、処置後のselectionによるbiasが生じる可能性があります。

---

## 3. 事前共変量

処置割付以前に決まっている変数のみをcovariateとして使用します。

使用した事前共変量は以下です。

- `recency`
- `history`
- `history_segment`
- `mens`
- `womens`
- `zip_code`
- `newbie`
- `channel`

一方、以下は処置後アウトカムなので、モデルの特徴量には使用しません。

- `visit`
- `conversion`
- `spend`

この制約はrandomization validation、heterogeneity analysis、uplift modelingのすべてで維持します。

---

## 4. データ品質監査

`sql/00_data_audit.sql` を用いて、分析前にデータ品質を確認しました。

主な確認項目は以下です。

- Row count
- Missingness
- Treatment domain
- Binary variable domain
- Numeric range
- Outcome consistency
- Duplicate-like rows

明示的なcustomer IDは存在しないため、全observed columnsが完全一致する行が存在しても、それだけを理由にduplicate customerとはみなしません。

異なる実験参加者が同一の観測値を持つ可能性があるため、**観測値が完全一致しているという理由だけで行を削除しない**方針としました。

---

## 5. ランダム化診断

`src/validate_randomization.py` を用いて、実験割付に重大な異常がないか確認しました。

### 5.1 Sample Ratio Mismatch

3群が概ね1:1:1で割り付けられているという帰無仮説をchi-square testで確認します。

$$
H_0:
\quad
p_{control}=p_{mens}=p_{womens}=\frac{1}{3}
$$

結果は、

- Chi-square = 0.203
- p-value = 0.904

であり、Sample Ratio Mismatchを示す証拠は確認されませんでした。

### 5.2 Standardized Mean Difference

事前共変量について、処置群間のbalanceをStandardized Mean Differenceで確認しました。

連続変数では、

$$
\mathrm{SMD}
=
\frac{\bar X_T-\bar X_C}
{\sqrt{(s_T^2+s_C^2)/2}}
$$

を使用します。

二値・カテゴリ変数についても、level indicatorに変換してpairwise balanceを評価します。

最大絶対SMDは約0.017で、

$$
|SMD|\ge0.10
$$

となる共変量はありませんでした。

したがって、**Sample Ratio Mismatchまたは重大な事前共変量の不均衡を示す証拠は確認されなかった**と解釈します。

なお、これはrandomizationが完全に成功したことを証明するものではありません。

---

## 6. 分析母集団

`sql/01_experiment_population.sql` でcanonical experiment populationを構築しました。

BigQuery table:

```text
ceus.experiment_population
```

処置ラベルは以下へ変換します。

```text
No E-Mail     -> control
Mens E-Mail   -> mens_email
Womens E-Mail -> womens_email
```

以下のeligibility flagを個別に管理します。

- `treatment_eligible`
- `pretreatment_eligible`
- `visit_eligible`
- `conversion_eligible`
- `spend_eligible`
- `outcome_consistent`
- `experiment_eligible`

`experiment_eligible`は処置割付と事前共変量の妥当性を基準とし、アウトカムの妥当性はmetric-specific eligibilityで管理します。

これにより、特定アウトカムの欠損やinvalidityによって他アウトカムの分析対象まで不必要に除外することを防ぎます。

---

## 7. A/B指標

`sql/02_ab_metrics.sql` では処置群ごとの記述統計のみを作成します。

Visit / Conversionについては、

- analysis N
- event count
- event rate
- mean
- standard deviation

を集計します。

Spendについては、

- analysis N
- total spend
- mean spend per randomized user
- standard deviation

を集計します。

このSQLではp-value、confidence interval、significance判定は行いません。

記述統計と推測統計の責務を分離するため、inferential analysisはPython側で実施します。

---

## 8. 平均処置効果

`src/estimate_ate.py` を用いて、以下の6つのITT effectを推定しました。

### 比較

- Men's Email vs Control
- Women's Email vs Control

### アウトカム

- Visit
- Conversion
- Spend

したがって、主要な検定familyは

$$
2\ treatments\times3\ outcomes=6\ tests
$$

です。

### 8.1 二値アウトカム

Visit / Conversionではdifference in proportionsを推定します。

$$
\widehat{ATE}
=
\hat p_T-\hat p_C
$$

信頼区間はunpooled standard errorを用います。

$$
SE_{CI}
=
\sqrt{
\frac{\hat p_T(1-\hat p_T)}{n_T}
+
\frac{\hat p_C(1-\hat p_C)}{n_C}
}
$$

仮説検定では帰無仮説下のpooled probabilityを用いたz-testを使用します。

### 8.2 Spend

Spendではdifference in meansを推定します。

$$
\widehat{ATE}
=
\bar Y_T-\bar Y_C
$$

分散が処置群で異なる可能性を考慮し、Welch inferenceを使用します。

標準誤差は、

$$
SE
=
\sqrt{
\frac{s_T^2}{n_T}
+
\frac{s_C^2}{n_C}
}
$$

です。

Spendの分布がzero-inflatedかつheavy-tailedであることから、percentile bootstrap confidence intervalも計算し、Welch CIとの整合性をrobustness checkとして利用します。

### 8.3 Multiple Testing

6つの事前定義されたTreatment × Outcome comparisonについて、Family-Wise Error Rateを制御するためHolm correctionを適用します。

---

## 9. サブグループ分析

`sql/03_segment_analysis.sql` で事前共変量別の記述的処置効果を作成します。

対象segmentは以下です。

- `recency`
- `history_segment`
- `mens`
- `womens`
- `newbie`
- `channel`
- `zip_code`

このSQLの目的は**仮説生成**であり、segment-level p-valueを大量に生成することではありません。

Raw subgroup liftだけでheterogeneityを断定しません。

---

## 10. 処置効果の異質性

`src/heterogeneity.py` でinteraction modelを推定します。

一般形は、

$$
Y_i
=
\beta_0
+\beta_1T_i
+\beta_2X_i
+\beta_3(T_iX_i)
+\varepsilon_i
$$

です。

処置効果の異質性はinteraction coefficient、

$$
\beta_3
$$

で評価します。

### 10.1 Robust Standard Error

OLS modelにHC3 robust standard errorを適用します。

二値アウトカムではLinear Probability Modelとして扱い、交互作用効果をoriginal outcome scaleで直接解釈します。

### 10.2 Targeted Follow-up Interaction

記述的サブグループ分析後に、以下のmoderator-treatment pairを選択しました。

- Women's Email × `womens`
- Men's Email × `mens`

各interactionをVisit / Conversion / Spendの3アウトカムについて評価し、合計6interaction testにHolm correctionを適用します。

ただし、これらはdescriptive subgroup review後に選択されたため、**確証的分析ではありません**。

Holm correctionはfollow-up family内のmultiplicityを制御しますが、仮説選択そのものによるpost-selection biasを除去するものではありません。

---

## 11. アップリフト・モデリング

`src/uplift_model.py` では、Conditional Average Treatment Effectの順位付けを目的としてT-Learnerを構築します。

3-arm treatmentを直接1つのbinary uplift modelに変換せず、以下を別問題として扱います。

- Men's Email vs Control
- Women's Email vs Control

### 11.1 T-Learner

処置群と対照群で別々のoutcome modelを学習します。

$$
\hat\mu_1(x)
=
\widehat{E}[Y\mid T=1,X=x]
$$

$$
\hat\mu_0(x)
=
\widehat{E}[Y\mid T=0,X=x]
$$

predicted upliftは、

$$
\hat\tau(x)
=
\hat\mu_1(x)-\hat\mu_0(x)
$$

とします。

モデルにはRandom Forestを使用します。

### 11.2 Train / Test Split

各binary treatment comparisonについてtrain / held-out testに分割します。

Treatment allocationとrare outcome eventを維持するため、Treatment × Outcome Eventでstratificationを行います。

Model fittingはtrain setのみ、uplift ranking evaluationはheld-out test setのみで行います。

### 11.3 評価指標

通常のpredictive AUCやRMSEをprimary metricとはしません。

アップリフトモデルの目的は、

> Treatment effectが大きいユーザーを上位に順位付けできるか

だからです。

使用指標は以下です。

- Qini
- AUUC
- Uplift@10%
- Uplift@20%
- Uplift@30%
- Uplift@50%

### 11.4 Transformed Outcome

held-out ranking evaluationではrandomized treatment propensityを用いたtransformed outcome、

$$
\psi_i
=
\frac{T_iY_i}{p}
-
\frac{(1-T_i)Y_i}{1-p}
$$

を利用します。

randomized assignment下では、

$$
E[\psi_i\mid X]
=
CATE(X)
$$

となります。

### 11.5 解釈

Predicted upliftは観測可能なindividual causal effectそのものではありません。

Individual Treatment Effectは各ユーザーについて同時に観測できないため、**predicted upliftはmodel-based estimate**として扱います。

---

## 12. 配信方針の価値評価

`src/policy_evaluation.py` ではuplift modelを実際の配信policyとして評価します。

比較方針は以下です。

- Send None
- Send All
- Top 10%
- Top 20%
- Top 30%
- Top 50%

### 12.1 Policy Value

deterministic policy $\pi(X)$ のvalueをInverse Propensity Weightingで推定します。

$$
V(\pi)
=
E\left[
\pi(X)\frac{TY}{e}
+
\{1-\pi(X)\}\frac{(1-T)Y}{1-e}
\right]
$$

ここで、

- $T$: randomized treatment indicator
- $Y$: observed outcome
- $e$: treatment propensity
- $\pi(X)$: model-based treatment rule

です。

### 12.2 Held-out Evaluation

Policy evaluationはuplift model trainingに使用していないheld-out observationsのみで実施します。

Training data上でpolicy valueを評価しません。

### 12.3 Bootstrap

Policy valueとpolicy differenceのuncertaintyはTreatment arm内でstratified bootstrapを行って推定します。

このbootstrapは、**既に学習済みのuplift modelを固定した条件下でのevaluation uncertainty**を評価します。

Model retraining uncertaintyまでは含みません。

### 12.4 Top-k Selection

Top 10%、20%、30%、50%を比較しますが、同じheld-out dataを見た後に最も良いTop-kを選び、それを「optimal policy」として確定しません。

この選択は探索的であり、新しいprospective dataでvalidationが必要です。

---

## 13. 配信コストの損益分岐点

Spend outcomeについて、delivery costを考慮したpolicy comparisonを行います。

Policy $\pi$ のtreatment rateを $r_\pi$、1配信あたりcostを $c$ とすると、

$$
\mathrm{NetValue}(\pi,c)
=
V(\pi)-cr_\pi
$$

と定義します。

### 13.1 Send Noneとの損益分岐点

$$
V(\pi)-cr_\pi
=
V(None)
$$

より、

$$
c^*
=
\frac{V(\pi)-V(None)}{r_\pi}
$$

を求めます。

### 13.2 Send Allとの損益分岐点

$$
V(\pi)-cr_\pi
=
V(All)-c
$$

より、

$$
c^*
=
\frac{V(All)-V(\pi)}{1-r_\pi}
$$

となります。

### 13.3 経済的制約

Hillstrom Datasetには以下がありません。

- 実際のdelivery cost
- gross margin
- contribution margin
- profit

したがって、break-even thresholdはprofit thresholdではなく、**revenue-equivalent break-even threshold**としてのみ解釈します。

実務上は粗利率 $m$ を用いて、

$$
\mathrm{NetValue}
=
m\times\mathrm{IncrementalSpend}
-\mathrm{DeliveryCost}
$$

で判断する必要があります。

---

## 14. 次回実験設計

Current uplift policyをそのまま本番導入せず、prospective RCTでvalidationします。

Women's Emailについて、

- Arm A: Send All
- Arm B: Frozen Top-10% Targeting Policy

とします。

Frozen policyでは以下をexperiment開始前に固定します。

- feature set
- model type
- model parameters
- trained model
- uplift scoring rule
- target fraction
- threshold

主要な推定対象は、

$$
\Delta
=
E[Spend\mid Targeting]
-
E[Spend\mid SendAll]
$$

です。

---

## 15. 検出力分析

`src/power_analysis.py` では、次回RCTに必要なsample sizeを感度分析します。

Spendはzero-inflatedかつhigh varianceなので、特定の小さいMDEだけを置かず、複数シナリオを評価します。

### 15.1 Planning SD

保守的に、

$$
\sigma_{plan}
=
\max(\sigma_{treatment},\sigma_{control})
$$

を使用します。

### 15.2 両側検定

Equal allocationの2-arm experimentについて、

$$
n
=
\frac{2\sigma^2(z_{1-\alpha/2}+z_{power})^2}{\delta^2}
$$

を用いて1群あたりのsample sizeを近似します。

### 15.3 非劣性検定

Targetingでは配信量を大幅に削減する代わりに、一定のSpend lossを許容する可能性があります。

$$
\Delta
=
V(Targeting)-V(SendAll)
$$

non-inferiority marginを $M>0$ とすると、

$$
H_0:\Delta\le-M
$$

$$
H_1:\Delta>-M
$$

とします。

必要sample sizeは、想定真値 $\Delta_{true}$ とnull boundaryとの差、

$$
\Delta_{true}+M
$$

に基づいて計算します。

### 15.4 Margin Selection

Non-inferiority marginは統計的に都合の良い値から選びません。

本来は、

- gross margin
- email delivery cost
- opportunity cost
- business tolerance

から事前に決めるべきbusiness parameterです。

---

## 16. Multiple Testing Policy

本分析では、すべてのp-valueを1つの巨大なfamilyとして補正しません。

### ATE Family

- 2 treatment comparisons
- 3 outcomes
- 6 tests

Holm correctionを適用します。

### Targeted Follow-up Heterogeneity Family

- 2 treatment-moderator hypotheses
- 3 outcomes
- 6 tests

Holm correctionを適用します。

ただし、仮説はpost-selectionされているため、探索的解釈を維持します。

---

## 17. 推論上のガードレール

本プロジェクトでは以下を明示的な分析ルールとします。

- Randomizationが「成功した」と断定しない
- Men's EmailとWomen's Emailの直接比較をしていないのに優劣を断定しない
- Descriptive subgroup patternを見た後に選択したinteractionをconfirmatoryと呼ばない
- Positive predicted upliftをindividual-level causal truthと解釈しない
- Held-out data上で最良だったTop-kをproduction policyとして即採用しない
- SpendをProfitと呼ばない
- 必要sample sizeを小さくするためにnon-inferiority marginを広げない

---

## 18. 再現性

分析pipelineは以下の順序で再実行できます。

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

BigQueryはGoogleSQLを使用します。

---

## 19. 方法論の要約

本プロジェクトでは、

$$
Data\ Quality
\rightarrow
Randomization\ Validation
\rightarrow
ATE
\rightarrow
Heterogeneity
\rightarrow
Uplift
\rightarrow
Policy\ Evaluation
\rightarrow
Experiment\ Design
$$

という順序で分析を構築しました。

目的は「Treatment effectが統計的に有意だった」で分析を終了することではありません。

最終的には、

- 誰に施策を実行すべきか
- その配信方針は一律配信より価値があるか
- 不確実性を考慮して本番導入できるか
- 次回実験にはどの程度のsample sizeが必要か

まで接続することを目的としています。
