# CRM実験分析とアップリフト・ターゲティング戦略

Hillstrom Email Marketing Datasetを用いて、CRMキャンペーンの**平均的な因果効果、効果の異質性、アップリフト・ターゲティング、配信方針の評価、次回実験のサンプルサイズ設計**まで一貫して分析したプロジェクトです。

> **CRMキャンペーンは本当にユーザー行動を改善したのか。全員に配信すべきか。それとも効果の高いユーザーだけに配信すべきか？**

単純なA/Bテストの有意差確認で終わらせず、因果効果を確認したうえで「誰に配信するか」「その配信方針は一律配信より価値があるか」「次回のランダム化比較試験で検証可能か」まで意思決定につなげています。

## 結論

### Men's Email

**一律配信（Send All）を維持する。**

- 対照群に対してVisit・Conversion・Spendのすべてで正のITT効果を確認
- 明確な処置効果の異質性は確認できず
- アップリフト順位付け性能も弱い
- 上位ユーザーだけに配信する方針は、一律配信より総購買金額を低下させた

現時点では、Men's Emailをターゲティング配信へ切り替える根拠は弱いと判断しました。

### Women's Email

**現時点では一律配信を維持し、上位10%ターゲティングを次回RCTの検証候補とする。**

- 対照群に対してVisit・Conversion・Spendのすべてで正のITT効果を確認
- 過去のWomen's商品購買履歴によってVisit・Conversionへの効果が異なる可能性を確認
- アップリフトモデルに順位付けシグナルあり
- 上位10%では高い増分Spendが観測された
- ただし、一律配信との総購買金額差には大きな不確実性が残る
- 現在のターゲティング方針はまだ前向き検証されていない

したがって、**ターゲティングは有望だが、現在の証拠だけで一律配信を置き換えるべきではない**という判断です。

## 分析フロー

```text
データ品質監査
    ↓
ランダム化診断
    ↓
分析母集団の構築
    ↓
A/B指標の集計
    ↓
平均処置効果（ATE）の推定
    ↓
処置効果の異質性分析
    ↓
アップリフト・モデリング
    ↓
配信方針の価値評価
    ↓
次回RCTの設計
    ↓
検出力・実行可能性分析
```

## データ

総ユーザー数は64,000です。実験は以下の3群で構成されます。

| 元のラベル | 分析用ラベル |
| --- | --- |
| No E-Mail | `control` |
| Mens E-Mail | `mens_email` |
| Womens E-Mail | `womens_email` |

主要なアウトカムは以下です。

- `visit`
- `conversion`
- `spend`

事前共変量として使用した変数は以下です。

- `recency`
- `history`
- `history_segment`
- `mens`
- `womens`
- `zip_code`
- `newbie`
- `channel`

`visit`、`conversion`、`spend`は処置後に決まるアウトカムなので、アップリフトモデルの特徴量には使用していません。

## 1. ランダム化診断

### Sample Ratio Mismatch（SRM）

| 群 | N |
| --- | ---: |
| 対照群 | 21,306 |
| Men's Email | 21,307 |
| Women's Email | 21,387 |

```text
Chi-square = 0.203
p-value    = 0.904
SRM flag   = False
```

事前共変量の群間バランスはStandardized Mean Difference（SMD）で確認しました。

連続変数のSMDは概ね次式で評価しています。

$$
\mathrm{SMD}
=
\frac{\bar X_T-\bar X_C}
{\sqrt{(s_T^2+s_C^2)/2}}
$$

最大絶対SMDは約0.017で、`|SMD| >= 0.10`となる変数はありませんでした。

したがって、**SRMまたは重大な観測済み事前共変量の不均衡を示す証拠は確認されなかった**と判断しています。これはランダム化が完全に成功したことを証明するものではありません。

## 2. 平均処置効果

Intent-to-Treat（ITT）として、Men's EmailとWomen's Emailをそれぞれ対照群と比較しました。

基本的な推定量は、処置群と対照群の平均差です。

$$
\widehat{ATE}=\bar Y_T-\bar Y_C
$$

2つの処置群 × 3つのアウトカム = 6比較に対してHolm補正を適用しています。

### Men's Email vs 対照群

| アウトカム | 対照群 | Men's Email | ATE |
| --- | ---: | ---: | ---: |
| Visit Rate | 10.62% | 18.28% | **+7.66pp** |
| Conversion Rate | 0.57% | 1.25% | **+0.68pp** |
| Spend / User | 0.653 | 1.423 | **+0.770** |

### Women's Email vs 対照群

| アウトカム | 対照群 | Women's Email | ATE |
| --- | ---: | ---: | ---: |
| Visit Rate | 10.62% | 15.14% | **+4.52pp** |
| Conversion Rate | 0.57% | 0.88% | **+0.31pp** |
| Spend / User | 0.653 | 1.077 | **+0.424** |

6比較すべてでHolm補正後も統計的に有意でした。Spendはゼロが非常に多く裾の長い分布なので、Welch法に加えてpercentile bootstrapによる信頼区間も確認しています。

なお、Men's EmailとWomen's Emailを直接比較する検定は行っていないため、「Men's Emailの方が統計的に優れている」とは主張していません。

## 3. 処置効果の異質性

事前共変量によって処置効果が変化するかを、交互作用項を含む回帰モデルで評価しました。

$$
Y_i
=
\beta_0
+\beta_1T_i
+\beta_2X_i
+\beta_3(T_iX_i)
+\varepsilon_i
$$

ここで、$\beta_3$ が効果の異質性を表す交互作用係数です。標準誤差にはHC3 robust standard errorを使用しました。

### Women's Email × 過去のWomen's商品購買履歴

```text
Visit interaction      = +6.20pp
95% CI                 = [4.95pp, 7.46pp]
Holm-adjusted p-value  < 0.001

Conversion interaction = +0.45pp
95% CI                  = [0.13pp, 0.77pp]
Holm-adjusted p-value   = 0.028
```

Spendでは有意な交互作用は確認できませんでした。また、Men's Email × 過去のMen's商品購買履歴でも十分な異質性の証拠は確認されませんでした。

これらの仮説は記述的なサブグループ分析を見た後に選択しているため、**確証的分析ではなく探索的なtargeted follow-up analysis**として扱っています。

## 4. アップリフト・モデリング

T-Learnerを用いて、以下を別々の二値処置問題として学習しました。

```text
Men's Email vs Control
Women's Email vs Control
```

処置群モデルと対照群モデルから条件付き平均処置効果を推定します。

$$
\hat\tau(x)
=
\hat\mu_1(x)-\hat\mu_0(x)
$$

ここで、$\hat\tau(x)$ は「そのユーザーにメールを送った場合にどれだけアウトカムが増えるとモデルが推定しているか」を表します。

特徴量は事前共変量のみに限定し、学習に使っていないheld-out sampleでQini、AUUC、Top-k upliftを評価しました。

| 処置 / アウトカム | Qini |
| --- | ---: |
| Men's / Conversion | -0.00023 |
| Men's / Spend | +0.00430 |
| Women's / Conversion | +0.00067 |
| Women's / Spend | +0.03670 |

Women's Emailでは順位付けシグナルが確認されました。ただし、predicted upliftは各ユーザーの真の個別因果効果そのものではなく、モデルによる推定値です。

## 5. 配信方針の価値評価

held-out predictionsを使い、以下の配信方針を比較しました。

- 配信しない（Send None）
- 全員に配信（Send All）
- 上位10%
- 上位20%
- 上位30%
- 上位50%

配信方針 $\pi(X)$ の価値はInverse Propensity Weighting（IPW）で推定しました。

$$
V(\pi)
=
E\left[
\pi(X)\frac{TY}{e}
+
\{1-\pi(X)\}\frac{(1-T)Y}{1-e}
\right]
$$

### Men's Email × Spend

| 配信方針 | Policy Value | vs Send All |
| --- | ---: | ---: |
| Send All | 1.581 | 0.000 |
| Top 10% | 0.826 | -0.755 |
| Top 20% | 0.893 | -0.688 |
| Top 30% | 0.946 | -0.635 |
| Top 50% | 1.213 | -0.367 |

Men's Emailでは、上位ユーザーだけに配信する方針は一律配信よりgross spendを明確に低下させました。

### Women's Email × Spend

| 配信方針 | Policy Value | vs Send All |
| --- | ---: | ---: |
| Send All | 1.156 | 0.000 |
| Top 10% | 0.855 | -0.301 |
| Top 20% | 0.838 | -0.317 |
| Top 30% | 0.868 | -0.287 |
| Top 50% | 0.895 | -0.261 |

上位10%と一律配信の差は以下です。

```text
Difference = -0.301
95% CI     = [-0.745, +0.114]
```

信頼区間が0をまたぐため、上位10%ターゲティングが一律配信と同等以上のgross spendを維持するとは結論できません。一方で、損失の大きさにも大きな不確実性があります。

## 6. 配信コストの損益分岐点

Hillstrom Datasetには実際の配信コストや粗利率が含まれていません。そのため架空の利益率を置かず、Spendと同じ単位で損益分岐となる配信コストを逆算しました。

配信方針 $\pi$ の配信率を $r_\pi$、1通あたり配信コストを $c$ とすると、簡略化した純価値は

$$
\mathrm{NetValue}(\pi,c)
=
V(\pi)-c r_\pi
$$

です。

上位10%ターゲティングと一律配信の損益分岐コストは

$$
c^*
=
\frac{V(\mathrm{All})-V(\pi)}{1-r_\pi}
$$

で表されます。Women's Email Top-10%の点推定では約0.334 / emailでした。

ただし、これは利益ベースの閾値ではありません。実務では粗利率 $m$ を用いて、

$$
\mathrm{NetValue}
=
m\times\mathrm{IncrementalSpend}
-\mathrm{DeliveryCost}
$$

と評価する必要があります。

## 7. 次回RCTの設計

Women's Emailの上位10%ターゲティングは、そのまま本番導入せず、新しいユーザーを対象とした前向きRCTで検証します。

- **Arm A:** 一律配信
- **Arm B:** 固定済みTop-10%アップリフト方針

実験開始前に、特徴量、モデル、ハイパーパラメータ、スコア計算方法、配信割合、閾値を固定します。

主要な推定対象は、

$$
\Delta
=
E[Spend\mid Targeting]
-
E[Spend\mid SendAll]
$$

です。

配信量を約90%削減する方針なので、単純なsuperiority testだけでなくnon-inferiority designを主要候補とします。

$$
H_0:\Delta\le -M
$$

$$
H_1:\Delta>-M
$$

ここで $M$ は、事業上許容できるSpend / Userの最大低下量です。必要サンプルサイズを小さくするために $M$ を広げるのではなく、粗利率、配信コスト、事業上の許容損失から事前に決める必要があります。

## 8. 検出力分析

Historical planning SDは16.76です。

### 両側検定のMDE感度分析

| Spend / User MDE | 必要総N |
| ---: | ---: |
| 0.10 | 881,424 |
| 0.20 | 220,356 |
| 0.30 | 97,936 |
| 0.40 | 55,090 |
| 0.50 | 35,258 |

### 非劣性検定: 真の差を0と仮定

| NI Margin | 必要総N |
| ---: | ---: |
| 0.10 | 694,298 |
| 0.20 | 173,576 |
| 0.30 | 77,146 |
| 0.40 | 43,394 |
| 0.50 | 27,772 |

一方、今回観測された $\Delta=-0.300664$ が将来も再現すると仮定すると、Margin 0.10 / 0.20 / 0.30では非劣性を達成できず、Margin 0.40では約703,610 users、Margin 0.50では約174,734 usersが必要です。

これは、**アップリフトのシグナルが見つかることと、その配信方針を実務投入できるだけの証拠を得られることは別問題**であることを示します。

## 技術スタック

- BigQuery / GoogleSQL
- Python
- pandas / NumPy / SciPy
- statsmodels
- scikit-learn
- pytest

## リポジトリ構成

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

## 再現手順

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

現在の回帰テスト結果:

```text
20 passed
```

## 詳細ドキュメント

- [意思決定メモ](docs/decision_memo.md) — 分析結果から何を意思決定するか
- [分析方法](docs/methodology.md) — どの統計手法・設計思想で分析したか
- [次回実験設計](docs/experiment_design.md) — Women's Top-10% targetingを次回RCTでどう前向き検証するか

## 分析上のガードレール

- SRM / covariate balanceだけで「ランダム化成功」と断定しない
- Men's EmailとWomen's Emailを直接比較していないため、どちらが統計的に優れているか断定しない
- 処置後変数でサブグループを作らない
- Conversionしたユーザーだけに限定してSpendを比較しない
- 記述的サブグループ分析後に選択した交互作用を確証的分析と呼ばない
- predicted upliftを個人レベルの真の因果効果と解釈しない
- 学習データ上でアップリフト方針を評価しない
- held-out sampleで最良だったTop-kを即座に本番方針として採用しない
- SpendをProfitと呼ばない
- サンプルサイズを小さくするために非劣性マージンを変更しない

## 最終メッセージ

このプロジェクトでは、A/Bテストの有意差確認で終了せず、因果推論、処置効果の異質性、causal ML、配信方針の評価、次回RCT設計まで接続しました。

**Men's Emailは一律配信を維持。Women's Emailも現時点では一律配信を維持し、上位10%ターゲティングは前向き検証の対象とする。**
