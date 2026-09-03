from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


DEFAULT_FRACTIONS = [
    0.10,
    0.20,
    0.30,
    0.50,
]

REQUIRED_COLUMNS = {
    "treatment",
    "outcome",
    "treatment_indicator",
    "observed_outcome",
    "predicted_uplift",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate held-out uplift targeting policies for the "
            "Hillstrom randomized email experiment."
        )
    )

    parser.add_argument(
        "--predictions",
        default="data/processed/uplift_predictions.csv",
        help="Held-out predictions produced by uplift_model.py.",
    )

    parser.add_argument(
        "--output-dir",
        default="data/processed",
        help="Directory for policy evaluation outputs.",
    )

    parser.add_argument(
        "--outcomes",
        nargs="+",
        default=[
            "conversion",
            "spend",
        ],
        help="Outcomes to evaluate.",
    )

    parser.add_argument(
        "--fractions",
        nargs="+",
        type=float,
        default=DEFAULT_FRACTIONS,
        help="Top-k targeting fractions.",
    )

    parser.add_argument(
        "--bootstrap-iterations",
        type=int,
        default=2000,
        help=(
            "Stratified bootstrap iterations for held-out "
            "policy-value uncertainty."
        ),
    )

    parser.add_argument(
        "--bootstrap-batch-size",
        type=int,
        default=25,
        help="Bootstrap processing batch size.",
    )

    parser.add_argument(
        "--alpha",
        type=float,
        default=0.05,
        help="Confidence interval alpha.",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed.",
    )

    return parser.parse_args()


def validate_args(
    args: argparse.Namespace,
) -> None:
    for fraction in args.fractions:
        if not 0 < fraction < 1:
            raise ValueError(
                "--fractions must be strictly between 0 and 1."
            )

    if args.bootstrap_iterations <= 0:
        raise ValueError(
            "--bootstrap-iterations must be positive."
        )

    if args.bootstrap_batch_size <= 0:
        raise ValueError(
            "--bootstrap-batch-size must be positive."
        )

    if not 0 < args.alpha < 1:
        raise ValueError(
            "--alpha must be between 0 and 1."
        )


def load_predictions(
    path: Path,
) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Predictions file not found: {path}"
        )

    df = pd.read_csv(
        path
    )

    missing = (
        REQUIRED_COLUMNS
        - set(
            df.columns
        )
    )

    if missing:
        raise ValueError(
            "Missing required prediction columns: "
            f"{sorted(missing)}"
        )

    for column in [
        "treatment_indicator",
        "observed_outcome",
        "predicted_uplift",
    ]:
        df[column] = pd.to_numeric(
            df[column],
            errors="raise",
        )

    return df


def validate_predictions(
    df: pd.DataFrame,
) -> None:
    treatment_values = set(
        df[
            "treatment_indicator"
        ]
        .dropna()
        .unique()
    )

    if not treatment_values.issubset(
        {0, 1}
    ):
        raise ValueError(
            "treatment_indicator must contain only 0/1."
        )

    if df[
        "predicted_uplift"
    ].isna().any():
        raise ValueError(
            "predicted_uplift contains missing values."
        )

    if df[
        "observed_outcome"
    ].isna().any():
        raise ValueError(
            "observed_outcome contains missing values."
        )

    if not (
        df[
            "treatment_indicator"
        ]
        == 1
    ).any():
        raise ValueError(
            "No treated observations found."
        )

    if not (
        df[
            "treatment_indicator"
        ]
        == 0
    ).any():
        raise ValueError(
            "No control observations found."
        )


def policy_name(
    fraction: float,
) -> str:
    percentage = int(
        round(
            100 * fraction
        )
    )

    return (
        f"top_{percentage}_pct"
    )


def make_policy_matrix(
    scores: np.ndarray,
    fractions: list[float],
) -> tuple[
    np.ndarray,
    list[str],
    list[float],
]:
    """
    Construct deterministic targeting rules using held-out
    predicted uplift rankings.

    No outcome information is used to form the policy.
    """
    scores = np.asarray(
        scores,
        dtype=float,
    )

    n = len(
        scores
    )

    if n == 0:
        raise ValueError(
            "Cannot build policies on an empty sample."
        )

    names = [
        "send_none",
        "send_all",
    ]

    columns = [
        np.zeros(
            n,
            dtype=float,
        ),
        np.ones(
            n,
            dtype=float,
        ),
    ]

    cutoffs = [
        np.nan,
        np.nan,
    ]

    # Stable ranking ensures reproducibility if scores tie.
    ranking = np.argsort(
        -scores,
        kind="mergesort",
    )

    for fraction in fractions:
        target_n = max(
            1,
            int(
                np.ceil(
                    fraction
                    * n
                )
            ),
        )

        decision = np.zeros(
            n,
            dtype=float,
        )

        targeted_indices = ranking[
            :target_n
        ]

        decision[
            targeted_indices
        ] = 1.0

        cutoff = float(
            scores[
                targeted_indices
            ].min()
        )

        names.append(
            policy_name(
                fraction
            )
        )

        columns.append(
            decision
        )

        cutoffs.append(
            cutoff
        )

    matrix = np.column_stack(
        columns
    )

    return (
        matrix,
        names,
        cutoffs,
    )


def ipw_policy_contributions(
    treatment: np.ndarray,
    outcome: np.ndarray,
    policies: np.ndarray,
    propensity: float,
) -> np.ndarray:
    """
    IPW policy-value contribution:

        V(pi)
          = E[
                pi(X) T Y / e
                +
                (1-pi(X)) (1-T) Y / (1-e)
              ]

    Since treatment assignment is randomized, this estimates
    expected outcome under each deterministic treatment policy.
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

    treated_component = (
        treatment
        * outcome
        / propensity
    )

    control_component = (
        (
            1.0
            - treatment
        )
        * outcome
        / (
            1.0
            - propensity
        )
    )

    return (
        policies
        * treated_component[
            :,
            None
        ]
        + (
            1.0
            - policies
        )
        * control_component[
            :,
            None
        ]
    )


def bootstrap_policy_values(
    contributions: np.ndarray,
    treatment: np.ndarray,
    iterations: int,
    batch_size: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """
    Stratified bootstrap within treatment assignment.

    This quantifies held-out evaluation uncertainty conditional
    on the already-trained uplift model.

    It does NOT include model-training uncertainty.
    """
    treatment = np.asarray(
        treatment,
        dtype=int,
    )

    treated_indices = np.flatnonzero(
        treatment == 1
    )

    control_indices = np.flatnonzero(
        treatment == 0
    )

    n_t = len(
        treated_indices
    )

    n_c = len(
        control_indices
    )

    n = (
        n_t
        + n_c
    )

    if n_t == 0 or n_c == 0:
        raise ValueError(
            "Bootstrap requires both treatment arms."
        )

    treated_contributions = contributions[
        treated_indices
    ]

    control_contributions = contributions[
        control_indices
    ]

    policy_count = contributions.shape[
        1
    ]

    bootstrap_values = np.empty(
        (
            iterations,
            policy_count,
        ),
        dtype=float,
    )

    weight_t = (
        n_t
        / n
    )

    weight_c = (
        n_c
        / n
    )

    completed = 0

    while completed < iterations:
        current_batch = min(
            batch_size,
            iterations - completed,
        )

        sampled_t = rng.integers(
            0,
            n_t,
            size=(
                current_batch,
                n_t,
            ),
        )

        sampled_c = rng.integers(
            0,
            n_c,
            size=(
                current_batch,
                n_c,
            ),
        )

        mean_t = (
            treated_contributions[
                sampled_t
            ]
            .mean(
                axis=1
            )
        )

        mean_c = (
            control_contributions[
                sampled_c
            ]
            .mean(
                axis=1
            )
        )

        batch_values = (
            weight_t
            * mean_t
            + weight_c
            * mean_c
        )

        bootstrap_values[
            completed:
            completed
            + current_batch
        ] = batch_values

        completed += (
            current_batch
        )

    return bootstrap_values


def quantile_interval(
    values: np.ndarray,
    alpha: float,
) -> tuple[
    float,
    float,
]:
    return (
        float(
            np.quantile(
                values,
                alpha / 2.0,
            )
        ),
        float(
            np.quantile(
                values,
                1.0
                - alpha / 2.0,
            )
        ),
    )


def evaluate_group(
    group: pd.DataFrame,
    treatment_name: str,
    outcome_name: str,
    fractions: list[float],
    bootstrap_iterations: int,
    bootstrap_batch_size: int,
    alpha: float,
    rng: np.random.Generator,
) -> pd.DataFrame:
    treatment = (
        group[
            "treatment_indicator"
        ]
        .to_numpy(
            dtype=int
        )
    )

    outcome = (
        group[
            "observed_outcome"
        ]
        .to_numpy(
            dtype=float
        )
    )

    scores = (
        group[
            "predicted_uplift"
        ]
        .to_numpy(
            dtype=float
        )
    )

    # Empirical held-out propensity.
    #
    # With this choice:
    #
    # Send All value  = observed treated mean
    # Send None value = observed control mean
    propensity = float(
        treatment.mean()
    )

    (
        policies,
        names,
        cutoffs,
    ) = make_policy_matrix(
        scores=scores,
        fractions=fractions,
    )

    contributions = (
        ipw_policy_contributions(
            treatment=treatment,
            outcome=outcome,
            policies=policies,
            propensity=propensity,
        )
    )

    policy_values = (
        contributions.mean(
            axis=0
        )
    )

    bootstrap_values = (
        bootstrap_policy_values(
            contributions=contributions,
            treatment=treatment,
            iterations=bootstrap_iterations,
            batch_size=bootstrap_batch_size,
            rng=rng,
        )
    )

    none_index = names.index(
        "send_none"
    )

    all_index = names.index(
        "send_all"
    )

    value_none = float(
        policy_values[
            none_index
        ]
    )

    value_all = float(
        policy_values[
            all_index
        ]
    )

    bootstrap_none = (
        bootstrap_values[
            :,
            none_index
        ]
    )

    bootstrap_all = (
        bootstrap_values[
            :,
            all_index
        ]
    )

    records: list[
        dict[str, Any]
    ] = []

    for index, name in enumerate(
        names
    ):
        value = float(
            policy_values[
                index
            ]
        )

        treatment_rate = float(
            policies[
                :,
                index
            ].mean()
        )

        incremental_vs_none = (
            value
            - value_none
        )

        incremental_vs_all = (
            value
            - value_all
        )

        value_ci_low, value_ci_high = (
            quantile_interval(
                bootstrap_values[
                    :,
                    index
                ],
                alpha=alpha,
            )
        )

        (
            incremental_none_ci_low,
            incremental_none_ci_high,
        ) = quantile_interval(
            bootstrap_values[
                :,
                index
            ]
            - bootstrap_none,
            alpha=alpha,
        )

        (
            incremental_all_ci_low,
            incremental_all_ci_high,
        ) = quantile_interval(
            bootstrap_values[
                :,
                index
            ]
            - bootstrap_all,
            alpha=alpha,
        )

        # ----------------------------------------------------
        # Break-even delivery cost
        #
        # Only economically interpretable for spend because
        # spend and delivery cost share monetary units.
        #
        # Versus Send None:
        #
        #   V(pi) - c*r = V(none)
        #
        #   c* = [V(pi)-V(none)] / r
        #
        #
        # Versus Send All:
        #
        #   V(pi) - c*r = V(all) - c
        #
        #   c* = [V(all)-V(pi)] / (1-r)
        #
        # For r < 1:
        #   targeting beats Send All when cost > c*
        #
        # If c* < 0, targeting already has higher gross value
        # than Send All before considering delivery cost.
        # ----------------------------------------------------

        break_even_vs_none = np.nan
        break_even_vs_all = np.nan

        if outcome_name == "spend":
            if treatment_rate > 0:
                break_even_vs_none = (
                    incremental_vs_none
                    / treatment_rate
                )

            if treatment_rate < 1:
                break_even_vs_all = (
                    (
                        value_all
                        - value
                    )
                    / (
                        1.0
                        - treatment_rate
                    )
                )

        records.append(
            {
                "treatment": treatment_name,
                "outcome": outcome_name,
                "policy": name,
                "evaluation_n": int(
                    len(
                        group
                    )
                ),
                "observed_treatment_propensity": (
                    propensity
                ),
                "treatment_rate": treatment_rate,
                "targeted_n": int(
                    policies[
                        :,
                        index
                    ].sum()
                ),
                "predicted_uplift_cutoff": (
                    cutoffs[
                        index
                    ]
                ),
                "policy_value": value,
                "policy_value_ci_low": (
                    value_ci_low
                ),
                "policy_value_ci_high": (
                    value_ci_high
                ),
                "incremental_vs_send_none": (
                    incremental_vs_none
                ),
                "incremental_vs_send_none_ci_low": (
                    incremental_none_ci_low
                ),
                "incremental_vs_send_none_ci_high": (
                    incremental_none_ci_high
                ),
                "incremental_vs_send_all": (
                    incremental_vs_all
                ),
                "incremental_vs_send_all_ci_low": (
                    incremental_all_ci_low
                ),
                "incremental_vs_send_all_ci_high": (
                    incremental_all_ci_high
                ),
                "break_even_delivery_cost_vs_none": (
                    break_even_vs_none
                ),
                "break_even_delivery_cost_vs_send_all": (
                    break_even_vs_all
                ),
                "gross_value_dominates_send_all": bool(
                    incremental_vs_all
                    > 0
                ),
            }
        )

    return pd.DataFrame(
        records
    )


def clean_json_value(
    value: Any,
) -> Any:
    if isinstance(
        value,
        dict,
    ):
        return {
            key: clean_json_value(
                item
            )
            for key, item
            in value.items()
        }

    if isinstance(
        value,
        list,
    ):
        return [
            clean_json_value(
                item
            )
            for item in value
        ]

    if isinstance(
        value,
        (
            np.integer,
            np.floating,
        ),
    ):
        value = value.item()

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
    ):
        if not np.isfinite(
            value
        ):
            return None

    return value


def build_summary(
    results: pd.DataFrame,
    predictions_path: str,
    bootstrap_iterations: int,
    alpha: float,
    seed: int,
) -> dict[str, Any]:
    spend_results = results[
        results[
            "outcome"
        ] == "spend"
    ]

    return clean_json_value(
        {
            "predictions_source": (
                predictions_path
            ),
            "evaluation_sample": (
                "Held-out observations produced by uplift_model.py"
            ),
            "estimator": (
                "Inverse-propensity-weighted policy value"
            ),
            "bootstrap": (
                "Stratified bootstrap within randomized treatment arms; "
                "conditional on the already-trained uplift model."
            ),
            "bootstrap_iterations": (
                bootstrap_iterations
            ),
            "alpha": alpha,
            "seed": seed,
            "policies": (
                results[
                    "policy"
                ]
                .drop_duplicates()
                .tolist()
            ),
            "spend_break_even_results": (
                spend_results[
                    [
                        "treatment",
                        "policy",
                        "treatment_rate",
                        "policy_value",
                        "incremental_vs_send_none",
                        "incremental_vs_send_all",
                        "break_even_delivery_cost_vs_none",
                        "break_even_delivery_cost_vs_send_all",
                    ]
                ]
                .to_dict(
                    orient="records"
                )
            ),
            "interpretation_guardrails": [
                (
                    "Policy comparisons use held-out predictions only."
                ),
                (
                    "Bootstrap intervals quantify evaluation-sample "
                    "uncertainty conditional on the fitted uplift model; "
                    "they do not include retraining uncertainty."
                ),
                (
                    "Top-k fractions are evaluated as a predefined policy "
                    "set. Selecting the best fraction after viewing these "
                    "results is exploratory and requires new validation."
                ),
                (
                    "Break-even delivery cost is economically interpretable "
                    "only for spend because both quantities are monetary."
                ),
                (
                    "Pairwise Men's Email and Women's Email policy results "
                    "must not be interpreted as a validated multi-arm policy."
                ),
            ],
        }
    )


def save_outputs(
    results: pd.DataFrame,
    summary: dict[str, Any],
    output_dir: Path,
) -> None:
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    results.to_csv(
        output_dir
        / "policy_evaluation.csv",
        index=False,
    )

    break_even = results[
        results[
            "outcome"
        ] == "spend"
    ].copy()

    break_even.to_csv(
        output_dir
        / "policy_break_even.csv",
        index=False,
    )

    with (
        output_dir
        / "policy_summary.json"
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
    results: pd.DataFrame,
) -> None:
    print(
        "\n=== Held-out Policy Evaluation ==="
    )

    display = results[
        [
            "treatment",
            "outcome",
            "policy",
            "treatment_rate",
            "policy_value",
            "incremental_vs_send_none",
            "incremental_vs_send_all",
        ]
    ].copy()

    display[
        "treatment_rate"
    ] = display[
        "treatment_rate"
    ].map(
        lambda value: (
            f"{100 * value:.1f}%"
        )
    )

    for column in [
        "policy_value",
        "incremental_vs_send_none",
        "incremental_vs_send_all",
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

    print(
        display.to_string(
            index=False
        )
    )

    spend = results[
        results[
            "outcome"
        ] == "spend"
    ].copy()

    if not spend.empty:
        print(
            "\n=== Spend Break-even Delivery Cost ==="
        )

        spend_display = spend[
            [
                "treatment",
                "policy",
                "treatment_rate",
                "break_even_delivery_cost_vs_none",
                "break_even_delivery_cost_vs_send_all",
                "gross_value_dominates_send_all",
            ]
        ].copy()

        spend_display[
            "treatment_rate"
        ] = spend_display[
            "treatment_rate"
        ].map(
            lambda value: (
                f"{100 * value:.1f}%"
            )
        )

        for column in [
            "break_even_delivery_cost_vs_none",
            "break_even_delivery_cost_vs_send_all",
        ]:
            spend_display[
                column
            ] = spend_display[
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
            spend_display.to_string(
                index=False
            )
        )

    print(
        "\nInterpretation:"
    )

    print(
        "- policy_value is the IPW estimate of expected outcome "
        "under that targeting rule."
    )

    print(
        "- incremental_vs_send_none is the causal gain relative "
        "to treating nobody."
    )

    print(
        "- incremental_vs_send_all measures whether targeting "
        "preserves or improves gross outcome relative to treating everyone."
    )

    print(
        "- For spend, break_even_delivery_cost_vs_send_all is the "
        "per-email cost above which the lower-volume targeting policy "
        "beats Send All in net value."
    )

    print(
        "- Do not automatically choose the best observed top-k fraction; "
        "that would be post-selection on the same held-out evaluation set."
    )


def main() -> None:
    args = parse_args()

    validate_args(
        args
    )

    predictions_path = Path(
        args.predictions
    )

    predictions = load_predictions(
        predictions_path
    )

    validate_predictions(
        predictions
    )

    print(
        f"Predictions source: {predictions_path}"
    )

    print(
        f"Loaded held-out prediction rows: {len(predictions)}"
    )

    result_frames: list[
        pd.DataFrame
    ] = []

    rng = np.random.default_rng(
        args.seed
    )

    groups = (
        predictions[
            predictions[
                "outcome"
            ].isin(
                args.outcomes
            )
        ]
        .groupby(
            [
                "treatment",
                "outcome",
            ],
            sort=True,
        )
    )

    for (
        treatment,
        outcome,
    ), group in groups:
        group = (
            group
            .reset_index(
                drop=True
            )
        )

        print(
            f"\nEvaluating: "
            f"{treatment} vs control / {outcome}"
        )

        results = evaluate_group(
            group=group,
            treatment_name=str(
                treatment
            ),
            outcome_name=str(
                outcome
            ),
            fractions=args.fractions,
            bootstrap_iterations=(
                args.bootstrap_iterations
            ),
            bootstrap_batch_size=(
                args.bootstrap_batch_size
            ),
            alpha=args.alpha,
            rng=rng,
        )

        result_frames.append(
            results
        )

    if not result_frames:
        raise ValueError(
            "No requested treatment/outcome groups found."
        )

    all_results = pd.concat(
        result_frames,
        ignore_index=True,
    )

    summary = build_summary(
        results=all_results,
        predictions_path=str(
            predictions_path
        ),
        bootstrap_iterations=(
            args.bootstrap_iterations
        ),
        alpha=args.alpha,
        seed=args.seed,
    )

    save_outputs(
        results=all_results,
        summary=summary,
        output_dir=Path(
            args.output_dir
        ),
    )

    print_report(
        all_results
    )


if __name__ == "__main__":
    main()