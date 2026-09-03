# Methodology

## 1. 分析目的

本プロジェクトでは、Hillstrom Email Marketing Datasetを用いて、CRMキャンペーンの因果効果とターゲティング配信の意思決定価値を評価する。

中心となるBusiness Questionは以下である。

> CRMキャンペーンは本当にユーザー行動を改善したのか。全員に配信すべきか。それとも効果のあるユーザーだけに配信すべきか？

この問いに対して、分析を以下の順序で進めた。

1. データ品質の確認
2. ランダム化の妥当性確認
3. 実験分析母集団の構築
4. A/B Testの記述統計
5. 平均処置効果の推定
6. Treatment Effect Heterogeneityの検証
7. Uplift Modeling
8. Policy Evaluation
9. Prospective Experiment Design
10. Power / Feasibility Analysis

分析では、単に予測精度の高いモデルを構築することではなく、**因果推論から意思決定まで一貫した分析フローを構築すること**を重視した。

---

## 2. データ

### 2.1 Dataset

使用データはHillstrom Email Marketing Datasetである。

観測単位はユーザーで、総行数は64,000行。

Treatmentは以下の3群から構成される。

* `No E-Mail`
* `Mens E-Mail`
* `Womens E-Mail`

分析用に以下へ正規化した。

* `control`
* `mens_email`
* `womens_email`

### 2.2 Outcome

主要outcomeは以下の3つ。

* `visit`
* `conversion`
* `spend`

`visit` と `conversion` はbinary outcome。

`spend` は連続値として扱う。

Spendについては、conversionしたユーザーだけに限定せず、**ランダム化された全ユーザーを分母としたSpend per randomized user**を評価する。

これはconversionがpost-treatment variableであり、

$$
E[Spend \mid Conversion=1]
$$

のような条件付き分析を行うと、treatment後のselectionによるbiasが発生するためである。

---

## 3. Pre-treatment Covariates

Treatment assignment以前に決まっている変数のみをcovariateとして使用する。

使用したpre-treatment featuresは以下。

* `recency`
* `history`
* `history_segment`
* `mens`
* `womens`
* `zip_code`
* `newbie`
* `channel`

一方、以下はpost-treatment outcomeであるため、model featureとして使用しない。

* `visit`
* `conversion`
* `spend`

この制約はrandomization validation、heterogeneity analysis、uplift modelingのすべてで維持する。

---

## 4. Data Quality Audit

`sql/00_data_audit.sql` を用いて、分析前にデータ品質を確認した。

主な確認項目は以下。

### 4.1 Row Count

総行数が64,000行であることを確認した。

### 4.2 Missingness

全列についてNULLまたはblank valueの有無を確認した。

### 4.3 Treatment Domain

Treatmentが期待する3群のみから構成されていることを確認した。

### 4.4 Binary Variable Domain

以下のbinary variableについて、

$$
\{0,1\}
$$

以外の値が存在しないことを確認した。

* `visit`
* `conversion`
* `mens`
* `womens`
* `newbie`

### 4.5 Numeric Range

`recency`、`history`、`spend`について最小値、最大値、平均、percentile等を確認した。

### 4.6 Outcome Consistency

以下の論理矛盾を確認した。

* `conversion = 1` かつ `spend <= 0`
* `conversion = 0` かつ `spend > 0`
* `conversion = 1` かつ `visit = 0`
* `spend < 0`

いずれも該当行はなかった。

### 4.7 Duplicate-like Rows

明示的なcustomer IDは存在しない。

全observed columnsが完全一致する行は存在するが、これらをduplicate customerとはみなさない。

異なる実験参加者が同じ観測値を持つ可能性があるため、

> 観測値が同一であることだけを理由に行を削除しない。

という方針を採用した。

---

## 5. Randomization Validation

`src/validate_randomization.py` を用いて、実験割付に重大な異常がないか確認した。

### 5.1 Sample Ratio Mismatch

3群が概ね1:1:1で割り付けられているという帰無仮説に対してchi-square testを実施した。

$$
H_0:
p_{control}
=
p_{mens}
=
p_{womens}
=
\frac{1}{3}
$$

結果：

* Chi-square = 0.203
* p-value = 0.904

Sample Ratio Mismatchを示す証拠は確認されなかった。

### 5.2 Standardized Mean Difference

pre-treatment covariatesについて、Treatment群間のbalanceをStandardized Mean Differenceで確認した。

連続変数では、

$$
SMD
=
\frac{
\bar X_T-\bar X_C
}{
\sqrt{
\frac{
s_T^2+s_C^2
}{2}
}
}
$$

を使用。

binary / categorical variableについても、level indicatorベースでpairwise balanceを評価した。

最大absolute SMDは約0.017であり、

$$
|SMD| \ge 0.10
$$

となるcovariateはなかった。

したがって、

> Sample Ratio Mismatchまたは重大なpre-treatment covariate imbalanceを示す証拠は確認されなかった。

と解釈した。

なお、これはrandomizationが完全に成功したことを証明するものではない。

---

## 6. Experiment Population

`sql/01_experiment_population.sql` でcanonical experiment populationを構築した。

BigQuery table:

```text
ceus.experiment_population
```

### 6.1 Treatment Normalization

Treatment labelを以下へ変換した。

```text
No E-Mail   -> control
Mens E-Mail -> mens_email
Womens E-Mail -> womens_email
```

### 6.2 Eligibility

以下のeligibility flagを個別に管理する。

* `treatment_eligible`
* `pretreatment_eligible`
* `visit_eligible`
* `conversion_eligible`
* `spend_eligible`
* `outcome_consistent`
* `experiment_eligible`

`experiment_eligible`はTreatmentとpre-treatment covariatesの妥当性を基準とする。

Outcomeのmissingnessやinvalidityはmetric-specific eligibilityで管理する。

この設計により、特定outcomeの欠損が他outcomeの分析対象まで不必要に除外することを防ぐ。

---

## 7. A/B Metrics

`sql/02_ab_metrics.sql` ではTreatment armごとのdescriptive metricsのみを作成する。

作成する主な指標は以下。

### Visit

* analysis N
* visit count
* visit rate
* mean
* standard deviation

### Conversion

* analysis N
* conversion count
* conversion rate
* mean
* standard deviation

### Spend

* analysis N
* total spend
* mean spend per randomized user
* standard deviation

このSQLではp-value、confidence interval、significance判定は行わない。

記述統計と推測統計の責務を分離するため、inferential analysisはPython側で行う。

---

## 8. Average Treatment Effect

`src/estimate_ate.py` を用いて、以下の6つのITT effectを推定した。

### Comparisons

* Men's Email vs Control
* Women's Email vs Control

### Outcomes

* Visit
* Conversion
* Spend

したがって、

$$
2 Treatments
\times
3 Outcomes
=
6 Tests
$$

を主要なATE familyとした。

### 8.1 Binary Outcomes

Visit / Conversionではdifference in proportionsを推定する。

$$
ATE
=
\hat p_T
-
\hat p_C
$$

confidence intervalはunpooled standard errorを用いる。

Hypothesis testではnull hypothesis下のpooled varianceを用いたz-testを使用する。

### 8.2 Spend

Spendではdifference in meansを推定する。

$$
ATE
=
\bar Y_T
-
\bar Y_C
$$

分散がTreatment群で異なる可能性を考慮し、Welch inferenceを使用する。

さらに、Spendの分布がzero-inflatedかつheavy-tailedであることから、percentile bootstrap confidence intervalも計算する。

Welch CIとbootstrap CIの整合性をrobustness checkとして利用する。

### 8.3 Multiple Testing

6つの事前定義されたTreatment × Outcome comparisonについて、Family-Wise Error Rateを制御するためHolm correctionを適用する。

Holm-adjusted p-valueを主要なmultiple-testing-adjusted inferenceとして使用する。

---

## 9. Segment Analysis

`sql/03_segment_analysis.sql` でpre-treatment covariates別のdescriptive treatment effectを作成する。

対象segment：

* `recency`
* `history_segment`
* `mens`
* `womens`
* `newbie`
* `channel`
* `zip_code`

各segmentについて、

```text
Treatment × Segment
```

単位で、

* N
* Visit rate
* Conversion rate
* Mean spend
* Control-relative descriptive lift

を計算する。

このSQLの目的は**hypothesis generation**であり、segment-level p-valueを大量に生成することではない。

Raw subgroup liftだけでheterogeneityを断定しない。

---

## 10. Treatment Effect Heterogeneity

`src/heterogeneity.py` でinteraction modelを推定する。

一般形は、

$$
Y_i
=
\beta_0
+
\beta_1T_i
+
\beta_2X_i
+
\beta_3(T_i\times X_i)
+
\epsilon_i
$$

とする。

Treatment effect heterogeneityはinteraction coefficient、

$$
\beta_3
$$

によって評価する。

### 10.1 Robust Standard Error

OLS modelにHC3 robust standard errorを適用する。

これはbinary outcomeを含め、interaction effectをoriginal outcome scaleで直接解釈するためである。

binary outcomeではLinear Probability Modelとして扱う。

### 10.2 Targeted Follow-up Interaction

descriptive subgroup analysis後に以下のmoderator-treatment pairを選択した。

* Women's Email × `womens`
* Men's Email × `mens`

各interactionを、

* Visit
* Conversion
* Spend

の3outcomeについて評価する。

合計6interaction testにHolm correctionを適用する。

ただし、これらはdescriptive subgroup review後に選択されたため、**confirmatoryではない**。

分析上は、

> targeted follow-up interaction analysis

として扱う。

Holm correctionはこのfollow-up family内のmultiplicityを制御するが、仮説選択そのものによるpost-selection biasを除去するものではない。

### 10.3 Exploratory Channel Analysis

`channel`についてはglobal Treatment × Channel interactionをjoint Wald testで評価する。

こちらはexploratory familyとしてtargeted follow-up familyとは分離して扱う。

---

## 11. Uplift Modeling

`src/uplift_model.py` では、Conditional Average Treatment Effectのrankingを目的としてT-Learnerを構築する。

3-arm treatmentを直接1つのbinary uplift modelに変換せず、以下を別問題として扱う。

* Men's Email vs Control
* Women's Email vs Control

### 11.1 T-Learner

Treatment armとControl armで別々のoutcome modelを学習する。

$$
\hat\mu_1(x)
=
\hat E[Y\mid T=1,X=x]
$$

$$
\hat\mu_0(x)
=
\hat E[Y\mid T=0,X=x]
$$

predicted upliftは、

$$
\hat\tau(x)
=
\hat\mu_1(x)
-
\hat\mu_0(x)
$$

とする。

モデルはRandom Forestを使用する。

### 11.2 Features

model featureはpre-treatment covariatesのみ。

Outcomeやpost-treatment variableは入力しない。

### 11.3 Train / Test Split

各binary treatment comparisonについてtrain / held-out testに分割する。

Treatment allocationとrare outcome eventを維持するため、Treatment × Outcome Eventでstratificationを行う。

Model fittingはtrain setのみ。

Uplift ranking evaluationはheld-out test setのみで行う。

### 11.4 Evaluation Metrics

通常のpredictive AUCやRMSEをprimary metricとはしない。

uplift modelの目的はoutcome predictionではなく、

> Treatment effectが大きいユーザーを上位にrankingできるか

だからである。

使用指標：

* Qini
* AUUC
* Uplift@10%
* Uplift@20%
* Uplift@30%
* Uplift@50%

### 11.5 Transformed Outcome

Held-out ranking evaluationではrandomized treatment propensityを用いたtransformed outcome、

$$
\psi_i
=
\frac{T_iY_i}{p}
-
\frac{(1-T_i)Y_i}{1-p}
$$

を利用する。

randomized assignment下では、

$$
E[\psi_i\mid X]
=
CATE(X)
$$

となる。

### 11.6 Interpretation

Predicted upliftは観測可能なindividual causal effectそのものではない。

Individual Treatment Effectは各ユーザーについて同時に観測できないため、

> predicted upliftはmodel-based estimate

として扱う。

Model usefulnessはheld-out ranking performanceで評価する。

---

## 12. Policy Evaluation

`src/policy_evaluation.py` ではuplift modelを実際の配信policyとして評価する。

比較policy：

* Send None
* Send All
* Top 10%
* Top 20%
* Top 30%
* Top 50%

### 12.1 Policy Value

deterministic policy \(\pi(X)\) のvalueをInverse Propensity Weightingで推定する。

$$
V(\pi)
=
E
\left[
\pi(X)
\frac{TY}{e}
+
(1-\pi(X))
\frac{(1-T)Y}{1-e}
\right]
$$

ここで、

* \(T\)：randomized treatment indicator
* \(Y\)：observed outcome
* \(e\)：treatment propensity
* \(\pi(X)\)：model-based treatment rule

とする。

### 12.2 Held-out Evaluation

Policy evaluationはuplift model trainingに使用していないheld-out observationsのみで実施する。

Training data上でpolicy valueを評価しない。

### 12.3 Bootstrap

Policy valueとpolicy differenceのuncertaintyはTreatment arm内でstratified bootstrapを行って推定する。

このbootstrapは、

> 既に学習済みのuplift modelを固定した条件下でのevaluation uncertainty

を評価する。

Model retraining uncertaintyまでは含まない。

### 12.4 Best Top-k Selection

Top 10%、20%、30%、50%をすべて比較するが、同じheld-out dataを見た後に最も良いTop-kを選び、

> optimal policy

として確定しない。

その選択はexploratoryであり、新しいprospective dataでvalidationが必要である。

---

## 13. Break-even Delivery Cost

Spend outcomeについて、delivery costを考慮したpolicy comparisonを行う。

Policy \(\pi\) のtreatment rateを、

$$
r_\pi
$$

1配信あたりcostを、

$$
c
$$

とすると、

$$
NetValue(\pi,c)
=
V(\pi)
-
cr_\pi
$$

と定義する。

### 13.1 Send NoneとのBreak-even

$$
V(\pi)-cr_\pi
=
V(None)
$$

より、

$$
c^*
=
\frac{
V(\pi)-V(None)
}{
r_\pi
}
$$

を求める。

### 13.2 Send AllとのBreak-even

$$
V(\pi)-cr_\pi
=
V(All)-c
$$

より、

$$
c^*
=
\frac{
V(All)-V(\pi)
}{
1-r_\pi
}
$$

となる。

Targeting policyのtreatment rateが1未満の場合、delivery costがこのthresholdを上回ると、gross outcomeを一部失ってもdelivery savingによってSend Allより高いnet valueを持つ可能性がある。

### 13.3 Economic Limitation

Hillstrom Datasetには以下が存在しない。

* 実際のdelivery cost
* gross margin
* contribution margin
* profit

したがって、break-even thresholdはprofit thresholdではなく、

> revenue-equivalent break-even threshold

としてのみ解釈する。

実務上は、

$$
NetValue
=
GrossMargin
\times
IncrementalSpend
-
DeliveryCost
$$

で判断する必要がある。

---

## 14. Prospective Experiment Design

Current uplift policyをそのまま本番導入せず、prospective RCTでvalidationする設計とする。

Women's Emailについて、

### Arm A

Send All

### Arm B

Frozen Top-10% Targeting Policy

とする。

Frozen policyでは以下をexperiment開始前に固定する。

* feature set
* model type
* model parameters
* trained model
* uplift scoring rule
* target fraction
* threshold

Outcomeを確認した後に変更しない。

Primary estimandは、

$$
\Delta
=
E[Spend\mid Targeting]
-
E[Spend\mid SendAll]
$$

とする。

---

## 15. Power Analysis

`src/power_analysis.py` では、次回RCTに必要なsample sizeを感度分析する。

Spendはzero-inflatedかつhigh varianceであるため、特定の小さなMDEだけを置かず、

* 0.10
* 0.20
* 0.30
* 0.40
* 0.50

のabsolute Spend per User differenceについてsample-size sensitivityを計算する。

### 15.1 Planning SD

planning varianceについては、

$$
\sigma_{plan}
=
\max(
\sigma_{treatment},
\sigma_{control}
)
$$

を使用する。

観測された小さい方のSDを利用してsample sizeを楽観的に見積もらないためである。

### 15.2 Two-sided Difference Detection

Equal allocationの2-arm experimentについて、

$$
n
=
\frac{
2\sigma^2
(z_{1-\alpha/2}+z_{power})^2
}{
\delta^2
}
$$

を用いてn per armを近似する。

### 15.3 Non-inferiority

Targetingでは配信量を大幅に削減する代わりに、一定のSpend lossを許容する可能性がある。

そのためPrimary design candidateとしてnon-inferiorityを検討する。

$$
\Delta
=
V(Targeting)
-
V(SendAll)
$$

non-inferiority marginを \(M>0\) とすると、

$$
H_0:
\Delta
\le
-M
$$

$$
H_1:
\Delta
>
-M
$$

とする。

必要sample sizeは、想定真値 \(\Delta_{true}\) とnull boundaryとの差、

$$
\Delta_{true}+M
$$

に基づいて計算する。

### 15.4 Margin Selection

Non-inferiority marginは統計的に都合の良い値から選ばない。

本来は、

* gross margin
* email delivery cost
* opportunity cost
* business tolerance

から事前に決定すべきbusiness parameterである。

現在のdatasetではこれらの情報がないため、複数marginについてsensitivity tableを提示する。

---

## 16. Multiple Testing Policy

本分析では、すべてのp-valueを1つの巨大なfamilyとして補正しない。

分析目的ごとにfamilyを分離する。

### ATE Family

* 2 treatment comparisons
* 3 outcomes
* 6 tests

Holm correctionを適用。

### Targeted Follow-up Heterogeneity Family

* 2 treatment-moderator hypotheses
* 3 outcomes
* 6 tests

Holm correctionを適用。

ただしpost-selectionされたhypothesesであるため、exploratory interpretationを維持する。

### Exploratory Channel Interaction

別familyとして扱う。

この分離により、異なるanalysis objectiveを持つ検定を機械的に同一familyへまとめない。

---

## 17. 推論上のGuardrails

本プロジェクトでは以下を明示的な分析ルールとした。

### Randomization

「Randomizationが成功した」と断定しない。

代わりに、

> SRMや重大なobserved covariate imbalanceを示す証拠は確認されなかった。

と表現する。

### Treatment Comparison

Men's EmailとWomen's EmailのControl relative ATEを比較しても、

> Men's EmailがWomen's Emailより有意に優れている

とは言わない。

直接比較していないためである。

### Heterogeneity

Descriptive subgroup patternを見た後に選択したinteractionはconfirmatoryと呼ばない。

### Uplift

Positive predicted upliftをindividual-level causal truthと解釈しない。

### Policy Selection

Held-out data上で最良だったTop-kを、そのままproduction policyとして採用しない。

### Economics

SpendをProfitと呼ばない。

### Power

必要sample sizeを小さくするためにnon-inferiority marginを拡大しない。

---

## 18. Reproducibility

分析pipelineは以下の順序で再実行できる。

```bash
bq query --use_legacy_sql=false < sql/00_data_audit.sql

python src/validate_randomization.py

bq query --use_legacy_sql=false < sql/01_experiment_population.sql

bq query --use_legacy_sql=false < sql/02_ab_metrics.sql

python src/estimate_ate.py

bq query --use_legacy_sql=false < sql/03_segment_analysis.sql

python src/heterogeneity.py

python src/uplift_model.py \
  --project hillstrom-experiment-20260828 \
  --table ceus.experiment_population

python src/policy_evaluation.py

python src/power_analysis.py
```

BigQueryはGoogleSQLを使用する。

---

## 19. 分析成果物

主要なprocessed outputsは以下。

### Randomization

```text
randomization_treatment_counts.csv
randomization_pairwise_balance.csv
randomization_covariate_summary.csv
randomization_validation_summary.json
```

### ATE

```text
ate_estimates.csv
ate_summary.json
```

### Heterogeneity

targeted follow-up interaction resultsおよびexploratory interaction results。

### Uplift

```text
uplift_model_metrics.csv
uplift_top_k.csv
uplift_curves.csv
uplift_predictions.csv
uplift_summary.json
```

### Policy

```text
policy_evaluation.csv
policy_break_even.csv
policy_summary.json
```

### Power

```text
power_mde_sensitivity.csv
power_noninferiority_sensitivity.csv
power_summary.json
```

---

## 20. Methodological Summary

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
Policy
\rightarrow
Experiment\ Design
$$

という順序で分析を構築した。

目的は、単に、

> Treatment effectが統計的に有意だった

で分析を終了することではない。

最終的には、

> 誰に施策を実行すべきか
> そのpolicyはSend Allより価値があるか
> 不確実性を考慮して本番導入できるか
> 次回実験にはどの程度のsample sizeが必要か

まで接続することを目的とした。

その結果、平均処置効果、heterogeneity、causal ML、policy evaluation、prospective experiment designを一貫した意思決定フレームワークとして統合した。
