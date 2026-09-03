# CRM配信戦略 意思決定メモ

## 1. 結論

現時点では、**Men's Email / Women's Emailともに一律配信（Send All）を基準方針として維持する**のが妥当です。

ただしWomen's Emailについては、過去のWomen's商品購買履歴による効果の異質性と、アップリフトモデルによる順位付けシグナルが確認されています。そのため、**将来的なターゲティング配信の候補**として検証を続けます。

一方、現在のデータだけでは上位10%ターゲティングが一律配信を上回るとは結論できません。したがって、Women's Emailのターゲティング配信は本番導入せず、モデル・対象割合・判定ルールを固定したうえで次回のランダム化比較試験で検証します。

---

## 2. ビジネス上の問い

本分析では、以下の問いに答えることを目的としました。

> CRMキャンペーンは本当にユーザー行動を改善したのか。全員に配信すべきか。それとも効果の高いユーザーだけに配信すべきか？

意思決定は次の3段階で行いました。

1. Email配信そのものに平均的な因果効果があるか
2. 効果がユーザー属性によって異なるか
3. アップリフトモデルを用いたターゲティングが一律配信より有利か

---

## 3. データと実験の妥当性

Hillstrom Email Marketing Datasetの64,000ユーザーを分析対象としました。

実験群は以下の3群です。

- 対照群: No E-Mail
- Men's Email
- Women's Email

ランダム化診断として、Sample Ratio Mismatch（SRM）と事前共変量バランスを確認しました。

### SRM

- Chi-square: 0.203
- p-value: 0.904
- SRM flag: False

処置割付に明確な異常は確認されませんでした。

### 事前共変量バランス

主要な事前共変量についてpairwise SMDを確認した結果、最大絶対SMDは約0.017で、一般的な目安である `|SMD| >= 0.10` に達する変数はありませんでした。

したがって、

> Sample Ratio Mismatchまたは重大な事前共変量の不均衡を示す証拠は確認されなかった。

と判断しました。

これはランダム化が「証明された」ことを意味するものではなく、観測可能な診断上、大きな問題が検出されなかったことを意味します。

---

## 4. 平均処置効果

Intent-to-Treat（ITT）として、対照群に対する各Email施策の平均処置効果を推定しました。

基本推定量は

$$
\widehat{ATE}=\bar Y_T-\bar Y_C
$$

です。

### Men's Email vs 対照群

| アウトカム | 対照群 | Men's Email | ATE |
| --- | ---: | ---: | ---: |
| Visit Rate | 10.62% | 18.28% | +7.66pp |
| Conversion Rate | 0.57% | 1.25% | +0.68pp |
| Spend / User | 0.653 | 1.423 | +0.770 |

3指標すべてで正の効果が確認され、Holm補正後も統計的に有意でした。

### Women's Email vs 対照群

| アウトカム | 対照群 | Women's Email | ATE |
| --- | ---: | ---: | ---: |
| Visit Rate | 10.62% | 15.14% | +4.52pp |
| Conversion Rate | 0.57% | 0.88% | +0.31pp |
| Spend / User | 0.653 | 1.077 | +0.424 |

Women's Emailも3指標すべてで正の効果が確認され、Holm補正後も統計的に有意でした。

### 判断

平均効果だけを見る限り、

> Emailを送らないより、Men's Email / Women's Emailを送った方がユーザー行動は改善する。

という結論を支持します。

なお、Men's Emailの点推定値はWomen's Emailより大きいですが、両者を直接比較する検定は行っていないため、「Men's Emailの方が統計的に優れている」とは結論していません。

---

## 5. 処置効果の異質性

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

ここで、$\beta_3$ が処置効果の異質性を表します。

記述的なサブグループ分析を確認した後に選択した交互作用なので、これらは確証的分析ではなく**探索的なtargeted follow-up analysis**として扱います。

### Women's Email × 過去のWomen's商品購買履歴

#### Visit

- Interaction effect: +6.20pp
- 95% CI: [4.95pp, 7.46pp]
- Holm-adjusted p-value: < 0.001

層別効果:

- `womens = 0`: +1.11pp
- `womens = 1`: +7.31pp

#### Conversion

- Interaction effect: +0.45pp
- 95% CI: [0.13pp, 0.77pp]
- Holm-adjusted p-value: 0.028

層別効果:

- `womens = 0`: +0.06pp
- `womens = 1`: +0.51pp

#### Spend

Spendについては交互作用の統計的証拠は十分ではありませんでした。

### Men's Email × 過去のMen's商品購買履歴

Visit、Conversion、Spendのいずれについても十分な交互作用の証拠は確認されませんでした。

### 判断

Women's Emailでは、

> 過去にWomen's商品を購入したユーザーほど、Visit / Conversionへの効果が大きい可能性がある。

というシグナルが得られました。

ただし、この仮説は記述的サブグループ分析の後に選択されたため、探索的結果として扱います。

---

## 6. アップリフト・モデリング

次に、平均効果ではなく

> 誰に送ると増分効果が大きいか

を推定するため、事前共変量のみを使ったT-Learnerを構築しました。

処置群と対照群でそれぞれアウトカムモデルを学習し、

$$
\hat\tau(x)
=
\hat\mu_1(x)-\hat\mu_0(x)
$$

としてpredicted upliftを計算します。

Men's Email vs Control、Women's Email vs Controlを別々の二値処置問題として学習し、held-out dataで評価しました。

### Men's Email

- Conversion Qini: -0.00023
- Spend Qini: +0.00430

ターゲティングによって明確に高upliftユーザーを識別できているとは言いにくい結果でした。

### Women's Email

- Conversion Qini: +0.00067
- Spend Qini: +0.03670

Top 20% Conversion:

- Observed uplift: +1.05pp
- 95% CI: [0.23pp, 1.88pp]

Top 10% Spend:

- Observed uplift: +2.486 / user
- 95% CI: [0.428, 4.544]

Women's Emailでは、Men's Emailより明確なアップリフト順位付けシグナルが観測されました。

ただし、Top-10%という割合は結果を確認した後に有望と判断したものであり、独立したvalidation sampleで確証された方針ではありません。

---

## 7. 配信方針の評価

held-out predictionsを用いて、以下の配信方針を比較しました。

- 配信しない（Send None）
- 全員に配信（Send All）
- Top 10%
- Top 20%
- Top 30%
- Top 50%

配信方針 $\pi(X)$ の価値はInverse Propensity Weightingで推定しました。

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

すべてのTop-k方針で一律配信よりgross spendが低く、その差の95% CIも0をまたぎませんでした。

したがって、Men's Emailでは現状、

> ターゲティングによってgross spendを維持しながら配信量を減らせる証拠はない。

と判断します。

### Women's Email × Spend

| 配信方針 | Policy Value | vs Send All |
| --- | ---: | ---: |
| Send All | 1.156 | 0.000 |
| Top 10% | 0.855 | -0.301 |
| Top 20% | 0.838 | -0.317 |
| Top 30% | 0.868 | -0.287 |
| Top 50% | 0.895 | -0.261 |

Top-10%と一律配信との差は、

- 点推定: -0.301
- 95% CI: [-0.745, +0.114]

でした。

したがって、

> Women's Email Top-10% targetingが一律配信と同等以上のgross spendを維持する

とは現時点では結論できません。

一方で信頼区間は0をまたいでおり、gross spend lossの大きさ自体にも不確実性があります。

---

## 8. 配信コストを考慮した意思決定

Hillstrom Datasetには実際のメール配信コスト、粗利率、利益率が含まれていません。

そのため、架空のコストを仮定するのではなく、Spendと同じ単位で損益分岐となる配信コストを計算しました。

配信方針 $\pi$ の配信率を $r_\pi$、1通あたり配信コストを $c$ とすると、簡略化した純価値は

$$
\mathrm{NetValue}(\pi,c)
=
V(\pi)-c r_\pi
$$

です。

Top-10% targetingと一律配信の損益分岐点は、

$$
c^*
=
\frac{V(\mathrm{All})-V(\pi)}{1-r_\pi}
$$

で表されます。

Women's Email Top-10%では、点推定で

$$
c^*\approx0.334
$$

でした。

つまり、Spendをそのまま経済価値として扱う単純化のもとでは、1配信あたりのコストが約0.334を超える場合、Top-10% targetingの方が一律配信より高いnet valueを持つ可能性があります。

ただし、これはprofit thresholdではありません。

実務では粗利率 $m$ を用いて、

$$
\mathrm{NetValue}
=
m\times\mathrm{IncrementalSpend}
-\mathrm{DeliveryCost}
$$

で評価する必要があります。

したがって、0.334は**revenue-equivalent break-even threshold**としてのみ解釈します。

---

## 9. 次回実験の設計

Women's Email targetingを本番導入する前に、prospective RCTを実施します。

### Arm A: 一律配信

Women's Emailを全eligible userに配信します。

### Arm B: 固定済みTop-10%ターゲティング方針

現在構築したアップリフトモデル、特徴量、model parameters、targeting thresholdを事前に固定し、uplift score上位約10%のみにWomen's Emailを配信します。

実験開始後にモデルやthresholdを変更しません。

### 主要な推定対象

$$
\Delta
=
E[Spend\mid Targeting]
-
E[Spend\mid SendAll]
$$

### 推奨する検定

配信量を90%削減する代わりに一定のSpend低下を許容する意思決定なので、単純なsuperiority testよりもnon-inferiority designが適しています。

$$
H_0:\Delta\le-M
$$

$$
H_1:\Delta>-M
$$

ここで $M$ は、事業上許容可能なSpend / Userの最大低下量です。

---

## 10. 検出力と実行可能性

Spendは非常にzero-inflatedかつ高分散であり、held-out dataではplanning SDが約16.76でした。

真の差を0と仮定した場合、80% power・片側alpha 5%のnon-inferiority designでは以下の必要サンプルサイズになります。

| NI Margin | 必要N / Arm | Total N |
| ---: | ---: | ---: |
| 0.10 | 347,149 | 694,298 |
| 0.20 | 86,788 | 173,576 |
| 0.30 | 38,573 | 77,146 |
| 0.40 | 21,697 | 43,394 |
| 0.50 | 13,886 | 27,772 |

さらに、今回観測された

$$
\Delta=-0.300664
$$

が真の差に近いと仮定すると、

- Margin 0.10: non-inferiority達成不可
- Margin 0.20: non-inferiority達成不可
- Margin 0.30: non-inferiority達成不可
- Margin 0.40: Total N 約703,610
- Margin 0.50: Total N 約174,734

となります。

Marginは必要サンプルサイズを小さくするために選ぶのではなく、粗利・配信コスト・機会費用などの事業上の許容範囲から事前に決定する必要があります。

---

## 11. 最終意思決定

### Men's Email

**Decision: 一律配信を維持**

理由:

- 対照群に対する平均処置効果は明確に正
- 強い処置効果の異質性の証拠なし
- アップリフト順位付け性能は弱い
- Top-k targetingは一律配信よりgross spendを有意に低下させた

現時点では、targeting modelを利用する根拠は弱いと判断します。

### Women's Email

**Decision: 一律配信を現行基準として維持し、ターゲティングは検証候補とする**

理由:

- 対照群に対する平均処置効果は正
- 過去のWomen's商品購買履歴によるVisit / Conversionのheterogeneity signalあり
- アップリフトモデルにpositive ranking signalあり
- 一部Top-kで高いincremental effectが観測された
- しかし一律配信とのgross spend差は不確実
- ターゲティング方針はprospective validationされていない
- 経済的に妥当なnon-inferiority marginを決めるための粗利・配信コスト情報が不足

したがって、

> Women's Email targetingは有望だが、現在の証拠だけで一律配信を置き換えるべきではない。

と判断します。

---

## 12. 推奨アクション

1. Men's Emailは一律配信を維持する。
2. Women's Emailも現時点では一律配信を維持する。
3. Women's Top-10% targetingを次回検証候補として固定する。
4. 実務上の粗利率・1配信あたりコストを取得する。
5. それらからbusiness-justified non-inferiority marginを事前設定する。
6. 必要サンプルサイズと実験期間が現実的か評価する。
7. 実行可能であれば、一律配信 vs 固定済みTop-10%方針のprospective RCTを実施する。
