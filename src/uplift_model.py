from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from google.cloud import bigquery
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import (
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


CONTROL = "control"

TREATMENTS = [
    "mens_email",
    "womens_email",
]

BINARY_OUTCOMES = {
    "visit",
    "conversion",
}

SUPPORTED_OUTCOMES = [
    "visit",
    "conversion",
    "spend",
]

NUMERIC_FEATURES = [
    "recency",
    "history",
    "mens",
    "womens",
    "newbie",
]

CATEGORICAL_FEATURES = [
    "history_segment",
    "zip_code",
    "channel",
]

FEATURES = (
    NUMERIC_FEATURES
    + CATEGORICAL_FEATURES
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Train and evaluate T-Learner uplift models for the "
            "Hillstrom randomized email experiment."
        )
    )

    parser.add_argument(
        "--project",
        default=os.getenv("GOOGLE_CLOUD_PROJECT"),
        help="Google Cloud project ID.",
    )

    parser.add_argument(
        "--table",
        default="ceus.experiment_population",
        help=(
            "BigQuery experiment population table. "
            "Use dataset.table or project.dataset.table."
        ),
    )

    parser.add_argument(
        "--outcomes",
        nargs="+",
        choices=SUPPORTED_OUTCOMES,
        default=[
            "conversion",
            "spend",
        ],
        help="Outcomes to model.",
    )

    parser.add_argument(
        "--output-dir",
        default="data/processed",
        help="Directory for output files.",
    )

    parser.add_argument(
        "--test-size",
        type=float,
        default=0.30,
        help="Held-out test fraction.",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed.",
    )

    parser.add_argument(
        "--n-estimators",
        type=int,
        default=300,
        help="Number of trees per T-Learner arm model.",
    )

    parser.add_argument(
        "--max-depth",
        type=int,
        default=8,
        help="Maximum random forest depth.",
    )

    parser.add_argument(
        "--min-samples-leaf",
        type=int,
        default=100,
        help="Minimum observations per leaf.",
    )

    parser.add_argument(
        "--top-k",
        nargs="+",
        type=float,
        default=[
            0.10,
            0.20,
            0.30,
            0.50,
        ],
        help="Fractions used for uplift@k evaluation.",
    )

    return parser.parse_args()


def resolve_table_id(
    project: str,
    table: str,
) -> str:
    if not re.fullmatch(
        r"[A-Za-z0-9_\-]+(?:\.[A-Za-z0-9_\-]+){1,2}",
        table,
    ):
        raise ValueError(
            "Expected dataset.table or project.dataset.table."
        )

    parts = table.split(".")

    if len(parts) == 3:
        return table

    if len(parts) == 2:
        return f"{project}.{table}"

    raise ValueError(
        f"Invalid table identifier: {table}"
    )


def validate_args(
    args: argparse.Namespace,
) -> None:
    if not 0 < args.test_size < 1:
        raise ValueError(
            "--test-size must be between 0 and 1."
        )

    if args.n_estimators <= 0:
        raise ValueError(
            "--n-estimators must be positive."
        )

    if args.min_samples_leaf <= 0:
        raise ValueError(
            "--min-samples-leaf must be positive."
        )

    for fraction in args.top_k:
        if not 0 < fraction <= 1:
            raise ValueError(
                "--top-k values must be in (0, 1]."
            )


def load_data(
    client: bigquery.Client,
    table_id: str,
) -> pd.DataFrame:
    """
    Load only pre-treatment features plus outcomes.

    No post-treatment variable is used as a model feature.
    """
    query = f"""
    SELECT
        treatment_group,

        -- Pre-treatment features
        recency,
        history,
        history_segment,
        mens,
        womens,
        zip_code,
        newbie,
        channel,

        -- Outcomes
        visit,
        conversion,
        spend,

        -- Outcome-specific eligibility
        visit_eligible,
        conversion_eligible,
        spend_eligible

    FROM `{table_id}`

    WHERE experiment_eligible
      AND outcome_consistent
      AND treatment_group IN (
          'control',
          'mens_email',
          'womens_email'
      )

    ORDER BY
        treatment_group,
        recency,
        history,
        history_segment,
        mens,
        womens,
        zip_code,
        newbie,
        channel,
        visit,
        conversion,
        spend
    """

    rows = client.query(
        query
    ).result()

    records = [
        dict(row.items())
        for row in rows
    ]

    if not records:
        raise ValueError(
            f"No rows returned from `{table_id}`."
        )

    df = pd.DataFrame.from_records(
        records
    )

    numeric_columns = [
        *NUMERIC_FEATURES,
        "visit",
        "conversion",
        "spend",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="raise",
        )

    return df


def validate_data(
    df: pd.DataFrame,
) -> None:
    expected_groups = {
        CONTROL,
        *TREATMENTS,
    }

    observed_groups = set(
        df["treatment_group"]
        .dropna()
        .unique()
    )

    if observed_groups != expected_groups:
        raise ValueError(
            "Unexpected treatment groups. "
            f"Observed={sorted(observed_groups)}"
        )

    post_treatment_features = (
        set(FEATURES)
        & {
            "visit",
            "conversion",
            "spend",
        }
    )

    if post_treatment_features:
        raise ValueError(
            "Post-treatment leakage detected in FEATURES: "
            f"{sorted(post_treatment_features)}"
        )

    if df[FEATURES].isna().any().any():
        missing = (
            df[FEATURES]
            .isna()
            .sum()
        )

        missing = missing[
            missing > 0
        ]

        raise ValueError(
            "Missing pre-treatment features: "
            f"{missing.to_dict()}"
        )

    for outcome in BINARY_OUTCOMES:
        values = set(
            df[outcome]
            .dropna()
            .unique()
        )

        if not values.issubset(
            {0, 1}
        ):
            raise ValueError(
                f"{outcome} contains invalid values: "
                f"{sorted(values)}"
            )

    if (
        df["spend"] < 0
    ).any():
        raise ValueError(
            "spend contains negative values."
        )


def make_preprocessor() -> ColumnTransformer:
    return ColumnTransformer(
        transformers=[
            (
                "numeric",
                "passthrough",
                NUMERIC_FEATURES,
            ),
            (
                "categorical",
                OneHotEncoder(
                    handle_unknown="ignore",
                ),
                CATEGORICAL_FEATURES,
            ),
        ],
        remainder="drop",
    )


def make_model(
    outcome: str,
    seed: int,
    n_estimators: int,
    max_depth: int,
    min_samples_leaf: int,
) -> Pipeline:
    if outcome in BINARY_OUTCOMES:
        estimator = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_leaf=min_samples_leaf,
            max_features=0.8,
            n_jobs=-1,
            random_state=seed,
        )
    else:
        estimator = RandomForestRegressor(
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_leaf=min_samples_leaf,
            max_features=0.8,
            n_jobs=-1,
            random_state=seed,
        )

    return Pipeline(
        steps=[
            (
                "preprocess",
                make_preprocessor(),
            ),
            (
                "model",
                estimator,
            ),
        ]
    )


def predict_expected_outcome(
    model: Pipeline,
    x: pd.DataFrame,
    outcome: str,
) -> np.ndarray:
    if outcome in BINARY_OUTCOMES:
        probabilities = model.predict_proba(
            x
        )

        classes = (
            model
            .named_steps["model"]
            .classes_
        )

        if 1 not in classes:
            raise ValueError(
                f"Model for {outcome} did not observe class 1."
            )

        positive_index = int(
            np.where(
                classes == 1
            )[0][0]
        )

        return probabilities[
            :,
            positive_index,
        ].astype(
            float
        )

    return model.predict(
        x
    ).astype(
        float
    )


def make_stratification_labels(
    data: pd.DataFrame,
    outcome: str,
) -> pd.Series:
    """
    Preserve both treatment allocation and rare outcome events
    across train/test.

    For spend, positive spend is used as the event indicator.
    """
    treatment = (
        data["treatment_indicator"]
        .astype(int)
        .astype(str)
    )

    if outcome in BINARY_OUTCOMES:
        event = (
            data[outcome]
            .astype(int)
            .astype(str)
        )
    else:
        event = (
            (
                data[outcome] > 0
            )
            .astype(int)
            .astype(str)
        )

    return (
        treatment
        + "_"
        + event
    )


def difference_in_means(
    data: pd.DataFrame,
    outcome: str,
) -> dict[str, float]:
    treated = (
        data.loc[
            data[
                "treatment_indicator"
            ] == 1,
            outcome,
        ]
        .to_numpy(
            dtype=float
        )
    )

    control = (
        data.loc[
            data[
                "treatment_indicator"
            ] == 0,
            outcome,
        ]
        .to_numpy(
            dtype=float
        )
    )

    if len(
        treated
    ) < 2 or len(
        control
    ) < 2:
        return {
            "treated_n": int(
                len(
                    treated
                )
            ),
            "control_n": int(
                len(
                    control
                )
            ),
            "uplift": np.nan,
            "standard_error": np.nan,
            "ci_low": np.nan,
            "ci_high": np.nan,
        }

    mean_t = float(
        treated.mean()
    )

    mean_c = float(
        control.mean()
    )

    uplift = (
        mean_t
        - mean_c
    )

    variance_t = float(
        treated.var(
            ddof=1
        )
    )

    variance_c = float(
        control.var(
            ddof=1
        )
    )

    standard_error = float(
        np.sqrt(
            variance_t
            / len(
                treated
            )
            + variance_c
            / len(
                control
            )
        )
    )

    critical = 1.959963984540054

    return {
        "treated_n": int(
            len(
                treated
            )
        ),
        "control_n": int(
            len(
                control
            )
        ),
        "treated_mean": mean_t,
        "control_mean": mean_c,
        "uplift": float(
            uplift
        ),
        "standard_error": (
            standard_error
        ),
        "ci_low": float(
            uplift
            - critical
            * standard_error
        ),
        "ci_high": float(
            uplift
            + critical
            * standard_error
        ),
    }


def transformed_outcome(
    treatment: np.ndarray,
    outcome: np.ndarray,
    propensity: float,
) -> np.ndarray:
    """
    Inverse-propensity transformed outcome:

        psi_i
          = T_i Y_i / p
            - (1-T_i) Y_i / (1-p)

    Under randomized assignment:

        E[psi | X] = CATE(X)
    """
    if not 0 < propensity < 1:
        raise ValueError(
            "Treatment propensity must be in (0, 1)."
        )

    treatment = np.asarray(
        treatment,
        dtype=float,
    )

    outcome = np.asarray(
        outcome,
        dtype=float,
    )

    return (
        treatment
        * outcome
        / propensity
        - (
            1.0
            - treatment
        )
        * outcome
        / (
            1.0
            - propensity
        )
    )


def trapezoid(
    y: np.ndarray,
    x: np.ndarray,
) -> float:
    if hasattr(
        np,
        "trapezoid",
    ):
        return float(
            np.trapezoid(
                y,
                x,
            )
        )

    return float(
        np.trapz(
            y,
            x,
        )
    )


def uplift_curve(
    predictions: pd.DataFrame,
) -> tuple[
    pd.DataFrame,
    dict[str, float],
]:
    """
    Rank held-out users by predicted uplift.

    Gain curve:

        G(k)
          = (1/N) * sum_{i in top-k} psi_i

    At 100% targeting:

        G(1) = test-set ATE

    Random targeting baseline:

        x * overall_ATE

    Qini here is defined as the area between the model gain curve
    and the random-targeting line.
    """
    ranked = (
        predictions
        .sort_values(
            "predicted_uplift",
            ascending=False,
        )
        .reset_index(
            drop=True
        )
    )

    treatment = (
        ranked[
            "treatment_indicator"
        ]
        .to_numpy(
            dtype=float
        )
    )

    outcome = (
        ranked[
            "observed_outcome"
        ]
        .to_numpy(
            dtype=float
        )
    )

    propensity = float(
        treatment.mean()
    )

    psi = transformed_outcome(
        treatment=treatment,
        outcome=outcome,
        propensity=propensity,
    )

    n = len(
        ranked
    )

    fraction = (
        np.arange(
            1,
            n + 1,
        )
        / n
    )

    cumulative_gain = (
        np.cumsum(
            psi
        )
        / n
    )

    overall_ate = float(
        psi.mean()
    )

    random_gain = (
        fraction
        * overall_ate
    )

    # Include origin.
    x = np.concatenate(
        [
            [0.0],
            fraction,
        ]
    )

    gain = np.concatenate(
        [
            [0.0],
            cumulative_gain,
        ]
    )

    random = np.concatenate(
        [
            [0.0],
            random_gain,
        ]
    )

    auuc = trapezoid(
        gain,
        x,
    )

    qini = trapezoid(
        gain - random,
        x,
    )

    curve = pd.DataFrame(
        {
            "fraction_targeted": x,
            "cumulative_gain": gain,
            "random_gain": random,
        }
    )

    # Save a compact ~101-point curve rather than every row.
    if len(
        curve
    ) > 101:
        indices = np.unique(
            np.linspace(
                0,
                len(
                    curve
                )
                - 1,
                101,
                dtype=int,
            )
        )

        curve = (
            curve
            .iloc[
                indices
            ]
            .reset_index(
                drop=True
            )
        )

    metrics = {
        "test_propensity": propensity,
        "test_ate": overall_ate,
        "auuc": auuc,
        "qini": qini,
    }

    return (
        curve,
        metrics,
    )


def evaluate_top_k(
    predictions: pd.DataFrame,
    fractions: list[float],
) -> pd.DataFrame:
    ranked = (
        predictions
        .sort_values(
            "predicted_uplift",
            ascending=False,
        )
        .reset_index(
            drop=True
        )
    )

    records: list[
        dict[str, Any]
    ] = []

    n = len(
        ranked
    )

    for fraction in fractions:
        k = max(
            1,
            int(
                np.ceil(
                    fraction
                    * n
                )
            ),
        )

        subset = (
            ranked
            .iloc[
                :k
            ]
            .copy()
        )

        subset_for_effect = (
            subset.rename(
                columns={
                    "observed_outcome":
                        "evaluation_outcome"
                }
            )
        )

        effect = difference_in_means(
            data=subset_for_effect,
            outcome="evaluation_outcome",
        )

        records.append(
            {
                "fraction_targeted": float(
                    fraction
                ),
                "targeted_n": int(
                    k
                ),
                "mean_predicted_uplift": float(
                    subset[
                        "predicted_uplift"
                    ].mean()
                ),
                "observed_uplift": effect[
                    "uplift"
                ],
                "observed_uplift_se": effect[
                    "standard_error"
                ],
                "observed_ci_low": effect[
                    "ci_low"
                ],
                "observed_ci_high": effect[
                    "ci_high"
                ],
                "treated_n": effect[
                    "treated_n"
                ],
                "control_n": effect[
                    "control_n"
                ],
            }
        )

    return pd.DataFrame(
        records
    )


def train_t_learner(
    data: pd.DataFrame,
    treatment: str,
    outcome: str,
    test_size: float,
    seed: int,
    n_estimators: int,
    max_depth: int,
    min_samples_leaf: int,
) -> tuple[
    pd.DataFrame,
    dict[str, Any],
]:
    """
    T-Learner:

        mu_1(x) = E[Y | T=1, X=x]
        mu_0(x) = E[Y | T=0, X=x]

        uplift(x) = mu_1(x) - mu_0(x)

    Models are trained only on the training split.

    Evaluation is performed only on held-out observations.
    """
    pair = (
        data.loc[
            data[
                "treatment_group"
            ].isin(
                [
                    CONTROL,
                    treatment,
                ]
            )
        ]
        .copy()
        .reset_index(
            drop=True
        )
    )

    eligibility_column = (
        f"{outcome}_eligible"
    )

    pair = (
        pair.loc[
            pair[
                eligibility_column
            ]
        ]
        .copy()
        .reset_index(
            drop=True
        )
    )

    pair[
        "treatment_indicator"
    ] = (
        pair[
            "treatment_group"
        ]
        == treatment
    ).astype(
        int
    )

    pair[
        "analysis_row_number"
    ] = np.arange(
        len(
            pair
        )
    )

    stratify = (
        make_stratification_labels(
            data=pair,
            outcome=outcome,
        )
    )

    (
        train_index,
        test_index,
    ) = train_test_split(
        np.arange(
            len(
                pair
            )
        ),
        test_size=test_size,
        random_state=seed,
        stratify=stratify,
    )

    train = (
        pair
        .iloc[
            train_index
        ]
        .copy()
    )

    test = (
        pair
        .iloc[
            test_index
        ]
        .copy()
    )

    train_treatment = train[
        train[
            "treatment_indicator"
        ] == 1
    ]

    train_control = train[
        train[
            "treatment_indicator"
        ] == 0
    ]

    if outcome in BINARY_OUTCOMES:
        for label, arm in [
            (
                "treatment",
                train_treatment,
            ),
            (
                "control",
                train_control,
            ),
        ]:
            classes = set(
                arm[
                    outcome
                ].unique()
            )

            if classes != {
                0,
                1,
            }:
                raise ValueError(
                    f"{treatment} / {outcome}: "
                    f"{label} training arm has classes "
                    f"{sorted(classes)}."
                )

    treatment_model = make_model(
        outcome=outcome,
        seed=seed + 1,
        n_estimators=n_estimators,
        max_depth=max_depth,
        min_samples_leaf=min_samples_leaf,
    )

    control_model = make_model(
        outcome=outcome,
        seed=seed + 2,
        n_estimators=n_estimators,
        max_depth=max_depth,
        min_samples_leaf=min_samples_leaf,
    )

    treatment_model.fit(
        train_treatment[
            FEATURES
        ],
        train_treatment[
            outcome
        ],
    )

    control_model.fit(
        train_control[
            FEATURES
        ],
        train_control[
            outcome
        ],
    )

    predicted_treatment = (
        predict_expected_outcome(
            model=treatment_model,
            x=test[
                FEATURES
            ],
            outcome=outcome,
        )
    )

    predicted_control = (
        predict_expected_outcome(
            model=control_model,
            x=test[
                FEATURES
            ],
            outcome=outcome,
        )
    )

    predicted_uplift = (
        predicted_treatment
        - predicted_control
    )

    predictions = test[
        [
            "analysis_row_number",
            "treatment_group",
            *FEATURES,
        ]
    ].copy()

    predictions[
        "treatment_indicator"
    ] = test[
        "treatment_indicator"
    ].to_numpy()

    predictions[
        "observed_outcome"
    ] = test[
        outcome
    ].to_numpy(
        dtype=float
    )

    predictions[
        "predicted_control_outcome"
    ] = predicted_control

    predictions[
        "predicted_treatment_outcome"
    ] = predicted_treatment

    predictions[
        "predicted_uplift"
    ] = predicted_uplift

    predictions[
        "comparison"
    ] = (
        f"{treatment}_vs_control"
    )

    predictions[
        "treatment"
    ] = treatment

    predictions[
        "outcome"
    ] = outcome

    metadata = {
        "comparison": (
            f"{treatment}_vs_control"
        ),
        "treatment": treatment,
        "control": CONTROL,
        "outcome": outcome,
        "model": "T-Learner Random Forest",
        "n_pair": int(
            len(
                pair
            )
        ),
        "n_train": int(
            len(
                train
            )
        ),
        "n_test": int(
            len(
                test
            )
        ),
        "train_treatment_n": int(
            len(
                train_treatment
            )
        ),
        "train_control_n": int(
            len(
                train_control
            )
        ),
        "mean_predicted_uplift": float(
            predicted_uplift.mean()
        ),
        "median_predicted_uplift": float(
            np.median(
                predicted_uplift
            )
        ),
        "positive_predicted_uplift_share": float(
            np.mean(
                predicted_uplift > 0
            )
        ),
    }

    return (
        predictions,
        metadata,
    )


def to_python(
    value: Any,
) -> Any:
    if isinstance(
        value,
        (
            np.integer,
            np.floating,
        ),
    ):
        return value.item()

    if isinstance(
        value,
        np.bool_,
    ):
        return bool(
            value
        )

    if isinstance(
        value,
        float,
    ) and np.isnan(
        value
    ):
        return None

    return value


def build_summary(
    source_table: str,
    args: argparse.Namespace,
    metrics: pd.DataFrame,
) -> dict[str, Any]:
    records: list[
        dict[str, Any]
    ] = []

    for row in metrics.to_dict(
        orient="records"
    ):
        records.append(
            {
                key: to_python(
                    value
                )
                for key, value
                in row.items()
            }
        )

    return {
        "source_table": source_table,
        "model": "T-Learner Random Forest",
        "treatments": TREATMENTS,
        "control": CONTROL,
        "outcomes": args.outcomes,
        "features": FEATURES,
        "feature_timing": "pre-treatment only",
        "test_size": args.test_size,
        "random_seed": args.seed,
        "n_estimators": args.n_estimators,
        "max_depth": args.max_depth,
        "min_samples_leaf": (
            args.min_samples_leaf
        ),
        "evaluation": {
            "method": (
                "Held-out ranking evaluation using randomized "
                "treatment assignment."
            ),
            "auuc": (
                "Area under the cumulative incremental-outcome "
                "gain curve."
            ),
            "qini": (
                "Area between the model gain curve and the "
                "random-targeting baseline."
            ),
            "uplift_at_k": (
                "Observed treatment-control outcome difference "
                "among the highest predicted-uplift fraction."
            ),
        },
        "results": records,
        "interpretation_guardrail": (
            "Individual predicted uplift is a model estimate, not an "
            "observable individual causal effect. Model usefulness should "
            "be judged by held-out uplift ranking metrics rather than "
            "ordinary predictive accuracy alone."
        ),
    }


def save_outputs(
    output_dir: Path,
    metrics: pd.DataFrame,
    top_k: pd.DataFrame,
    curves: pd.DataFrame,
    predictions: pd.DataFrame,
    summary: dict[str, Any],
) -> None:
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    metrics.to_csv(
        output_dir
        / "uplift_model_metrics.csv",
        index=False,
    )

    top_k.to_csv(
        output_dir
        / "uplift_top_k.csv",
        index=False,
    )

    curves.to_csv(
        output_dir
        / "uplift_curves.csv",
        index=False,
    )

    predictions.to_csv(
        output_dir
        / "uplift_predictions.csv",
        index=False,
    )

    with (
        output_dir
        / "uplift_summary.json"
    ).open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            summary,
            file,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )


def print_report(
    metrics: pd.DataFrame,
    top_k: pd.DataFrame,
) -> None:
    print(
        "\n=== Uplift Model Evaluation ==="
    )

    display = metrics[
        [
            "treatment",
            "outcome",
            "n_train",
            "n_test",
            "test_ate",
            "mean_predicted_uplift",
            "positive_predicted_uplift_share",
            "auuc",
            "qini",
        ]
    ].copy()

    for column in [
        "test_ate",
        "mean_predicted_uplift",
        "auuc",
        "qini",
    ]:
        display[
            column
        ] = display[
            column
        ].map(
            lambda value: (
                f"{value:.6f}"
            )
        )

    display[
        "positive_predicted_uplift_share"
    ] = display[
        "positive_predicted_uplift_share"
    ].map(
        lambda value: (
            f"{100 * value:.2f}%"
        )
    )

    print(
        display.to_string(
            index=False
        )
    )

    print(
        "\n=== Uplift@K ==="
    )

    top_display = top_k[
        [
            "treatment",
            "outcome",
            "fraction_targeted",
            "targeted_n",
            "observed_uplift",
            "observed_ci_low",
            "observed_ci_high",
        ]
    ].copy()

    top_display[
        "fraction_targeted"
    ] = top_display[
        "fraction_targeted"
    ].map(
        lambda value: (
            f"{100 * value:.0f}%"
        )
    )

    for column in [
        "observed_uplift",
        "observed_ci_low",
        "observed_ci_high",
    ]:
        top_display[
            column
        ] = top_display[
            column
        ].map(
            lambda value: (
                "NA"
                if pd.isna(
                    value
                )
                else f"{value:.6f}"
            )
        )

    print(
        top_display.to_string(
            index=False
        )
    )

    print(
        "\nInterpretation:"
    )

    print(
        "- Positive Qini means the held-out ranking beats random "
        "targeting on the chosen outcome."
    )

    print(
        "- Uplift@K should be compared with the overall test ATE."
    )

    print(
        "- Ordinary AUC / RMSE is not the primary success criterion "
        "for treatment targeting."
    )

    print(
        "- Negative predicted uplift does not by itself prove that "
        "treatment harms that individual."
    )


def main() -> None:
    args = parse_args()

    validate_args(
        args
    )

    client = bigquery.Client(
        project=args.project,
    )

    table_id = resolve_table_id(
        project=client.project,
        table=args.table,
    )

    print(
        f"Source table: `{table_id}`"
    )

    df = load_data(
        client=client,
        table_id=table_id,
    )

    validate_data(
        df
    )

    print(
        f"Loaded experiment rows: {len(df)}"
    )

    metric_records: list[
        dict[str, Any]
    ] = []

    top_k_frames: list[
        pd.DataFrame
    ] = []

    curve_frames: list[
        pd.DataFrame
    ] = []

    prediction_frames: list[
        pd.DataFrame
    ] = []

    for treatment_index, treatment in enumerate(
        TREATMENTS
    ):
        for outcome_index, outcome in enumerate(
            args.outcomes
        ):
            model_seed = (
                args.seed
                + 100
                * treatment_index
                + 10
                * outcome_index
            )

            print(
                f"\nTraining: "
                f"{treatment} vs {CONTROL} / {outcome}"
            )

            (
                predictions,
                metadata,
            ) = train_t_learner(
                data=df,
                treatment=treatment,
                outcome=outcome,
                test_size=args.test_size,
                seed=model_seed,
                n_estimators=args.n_estimators,
                max_depth=args.max_depth,
                min_samples_leaf=(
                    args.min_samples_leaf
                ),
            )

            (
                curve,
                curve_metrics,
            ) = uplift_curve(
                predictions=predictions
            )

            metric_record = {
                **metadata,
                **curve_metrics,
            }

            metric_records.append(
                metric_record
            )

            top_k = evaluate_top_k(
                predictions=predictions,
                fractions=args.top_k,
            )

            top_k[
                "treatment"
            ] = treatment

            top_k[
                "comparison"
            ] = (
                f"{treatment}_vs_control"
            )

            top_k[
                "outcome"
            ] = outcome

            top_k_frames.append(
                top_k
            )

            curve[
                "treatment"
            ] = treatment

            curve[
                "comparison"
            ] = (
                f"{treatment}_vs_control"
            )

            curve[
                "outcome"
            ] = outcome

            curve_frames.append(
                curve
            )

            prediction_frames.append(
                predictions
            )

    metrics = pd.DataFrame(
        metric_records
    )

    top_k_results = pd.concat(
        top_k_frames,
        ignore_index=True,
    )

    curves = pd.concat(
        curve_frames,
        ignore_index=True,
    )

    all_predictions = pd.concat(
        prediction_frames,
        ignore_index=True,
    )

    summary = build_summary(
        source_table=table_id,
        args=args,
        metrics=metrics,
    )

    save_outputs(
        output_dir=Path(
            args.output_dir
        ),
        metrics=metrics,
        top_k=top_k_results,
        curves=curves,
        predictions=all_predictions,
        summary=summary,
    )

    print_report(
        metrics=metrics,
        top_k=top_k_results,
    )


if __name__ == "__main__":
    main()