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
from scipy import stats


CONTROL = "control"

TREATMENTS = [
    "mens_email",
    "womens_email",
]

BINARY_OUTCOMES = [
    "visit",
    "conversion",
]

CONTINUOUS_OUTCOMES = [
    "spend",
]

ALL_OUTCOMES = BINARY_OUTCOMES + CONTINUOUS_OUTCOMES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Estimate intention-to-treat effects for the Hillstrom "
            "randomized email experiment."
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
            "BigQuery experiment-population table. "
            "Use dataset.table with --project, or project.dataset.table."
        ),
    )

    parser.add_argument(
        "--output-dir",
        default="data/processed",
        help="Directory for output files.",
    )

    parser.add_argument(
        "--alpha",
        type=float,
        default=0.05,
        help="Two-sided inference alpha.",
    )

    parser.add_argument(
        "--bootstrap-iterations",
        type=int,
        default=5000,
        help="Bootstrap iterations for spend ATE confidence intervals.",
    )

    parser.add_argument(
        "--bootstrap-batch-size",
        type=int,
        default=100,
        help="Bootstrap resampling batch size.",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for bootstrap reproducibility.",
    )

    return parser.parse_args()


def resolve_table_id(
    project: str | None,
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
        if not project:
            raise ValueError(
                "--project is required when table is dataset.table."
            )

        return f"{project}.{table}"

    raise ValueError(f"Invalid table identifier: {table}")


def load_experiment_data(
    client: bigquery.Client,
    table_id: str,
) -> pd.DataFrame:
    query = f"""
    SELECT
        treatment_group,
        visit,
        conversion,
        spend
    FROM `{table_id}`
    WHERE experiment_eligible
      AND outcome_consistent
      AND treatment_group IN (
          'control',
          'mens_email',
          'womens_email'
      )
    """

    rows = client.query(query).result()

    records = [dict(row.items()) for row in rows]

    if not records:
        raise ValueError(
            f"No experiment rows returned from `{table_id}`."
        )

    df = pd.DataFrame.from_records(records)

    df["visit"] = pd.to_numeric(
        df["visit"],
        errors="raise",
    )

    df["conversion"] = pd.to_numeric(
        df["conversion"],
        errors="raise",
    )

    df["spend"] = pd.to_numeric(
        df["spend"],
        errors="raise",
    )

    return df


def validate_data(df: pd.DataFrame) -> None:
    expected_groups = {
        CONTROL,
        *TREATMENTS,
    }

    observed_groups = set(
        df["treatment_group"].dropna().unique()
    )

    if observed_groups != expected_groups:
        raise ValueError(
            "Unexpected treatment groups. "
            f"Observed={sorted(observed_groups)}"
        )

    for outcome in BINARY_OUTCOMES:
        values = set(
            df[outcome].dropna().unique()
        )

        if not values.issubset({0, 1}):
            raise ValueError(
                f"{outcome} contains values outside {{0, 1}}: "
                f"{sorted(values)}"
            )

    if df["spend"].isna().any():
        raise ValueError("spend contains missing values.")

    if (df["spend"] < 0).any():
        raise ValueError("spend contains negative values.")


def two_sided_normal_p_value(
    z: float,
) -> float:
    return float(
        2.0 * stats.norm.sf(abs(z))
    )


def estimate_binary_effect(
    treatment_values: np.ndarray,
    control_values: np.ndarray,
    alpha: float,
) -> dict[str, float]:
    """
    Difference in proportions:

        ATE = p_treatment - p_control

    CI:
        unpooled standard error

    Hypothesis test:
        pooled two-sample proportion z-test under H0.
    """
    treatment_values = np.asarray(
        treatment_values,
        dtype=float,
    )

    control_values = np.asarray(
        control_values,
        dtype=float,
    )

    n_t = len(treatment_values)
    n_c = len(control_values)

    if n_t == 0 or n_c == 0:
        raise ValueError("Empty treatment or control sample.")

    successes_t = float(treatment_values.sum())
    successes_c = float(control_values.sum())

    p_t = successes_t / n_t
    p_c = successes_c / n_c

    ate = p_t - p_c

    relative_lift = (
        ate / p_c
        if p_c != 0
        else np.nan
    )

    # Unpooled standard error for the confidence interval.
    se = np.sqrt(
        p_t * (1.0 - p_t) / n_t
        + p_c * (1.0 - p_c) / n_c
    )

    z_critical = stats.norm.ppf(
        1.0 - alpha / 2.0
    )

    ci_low = ate - z_critical * se
    ci_high = ate + z_critical * se

    # Pooled standard error under the null hypothesis p_t = p_c.
    pooled_probability = (
        successes_t + successes_c
    ) / (n_t + n_c)

    null_se = np.sqrt(
        pooled_probability
        * (1.0 - pooled_probability)
        * (1.0 / n_t + 1.0 / n_c)
    )

    if np.isclose(null_se, 0.0):
        z_stat = 0.0 if np.isclose(ate, 0.0) else np.inf
    else:
        z_stat = ate / null_se

    p_value = two_sided_normal_p_value(
        z_stat
    )

    return {
        "control_n": int(n_c),
        "treatment_n": int(n_t),
        "control_mean": float(p_c),
        "treatment_mean": float(p_t),
        "ate": float(ate),
        "relative_lift": float(relative_lift),
        "standard_error": float(se),
        "ci_low": float(ci_low),
        "ci_high": float(ci_high),
        "test_statistic": float(z_stat),
        "degrees_of_freedom": np.nan,
        "p_value": float(p_value),
    }


def welch_degrees_of_freedom(
    variance_t: float,
    variance_c: float,
    n_t: int,
    n_c: int,
) -> float:
    term_t = variance_t / n_t
    term_c = variance_c / n_c

    numerator = (term_t + term_c) ** 2

    denominator = (
        (term_t**2) / (n_t - 1)
        + (term_c**2) / (n_c - 1)
    )

    if denominator <= 0.0:
        return np.inf

    return float(numerator / denominator)


def estimate_continuous_effect(
    treatment_values: np.ndarray,
    control_values: np.ndarray,
    alpha: float,
) -> dict[str, float]:
    """
    Difference in means with Welch inference.

        ATE = mean(Y_treatment) - mean(Y_control)

    The spend distribution is zero-inflated and skewed, so a
    non-parametric bootstrap CI is calculated separately as a
    robustness check.
    """
    treatment_values = np.asarray(
        treatment_values,
        dtype=float,
    )

    control_values = np.asarray(
        control_values,
        dtype=float,
    )

    n_t = len(treatment_values)
    n_c = len(control_values)

    if n_t < 2 or n_c < 2:
        raise ValueError(
            "At least two observations per arm are required."
        )

    mean_t = float(
        treatment_values.mean()
    )

    mean_c = float(
        control_values.mean()
    )

    ate = mean_t - mean_c

    relative_lift = (
        ate / mean_c
        if mean_c != 0
        else np.nan
    )

    variance_t = float(
        treatment_values.var(ddof=1)
    )

    variance_c = float(
        control_values.var(ddof=1)
    )

    se = np.sqrt(
        variance_t / n_t
        + variance_c / n_c
    )

    df = welch_degrees_of_freedom(
        variance_t=variance_t,
        variance_c=variance_c,
        n_t=n_t,
        n_c=n_c,
    )

    t_critical = stats.t.ppf(
        1.0 - alpha / 2.0,
        df=df,
    )

    ci_low = ate - t_critical * se
    ci_high = ate + t_critical * se

    if np.isclose(se, 0.0):
        t_stat = 0.0 if np.isclose(ate, 0.0) else np.inf
    else:
        t_stat = ate / se

    p_value = float(
        2.0
        * stats.t.sf(
            abs(t_stat),
            df=df,
        )
    )

    return {
        "control_n": int(n_c),
        "treatment_n": int(n_t),
        "control_mean": mean_c,
        "treatment_mean": mean_t,
        "ate": float(ate),
        "relative_lift": float(relative_lift),
        "standard_error": float(se),
        "ci_low": float(ci_low),
        "ci_high": float(ci_high),
        "test_statistic": float(t_stat),
        "degrees_of_freedom": float(df),
        "p_value": float(p_value),
    }


def bootstrap_mean_difference(
    treatment_values: np.ndarray,
    control_values: np.ndarray,
    iterations: int,
    batch_size: int,
    alpha: float,
    rng: np.random.Generator,
) -> tuple[float, float]:
    """
    Percentile bootstrap CI for the difference in mean spend.

    Resampling is performed independently within each randomized arm.

    Processing in batches avoids allocating a full
    iterations x sample_size matrix.
    """
    treatment_values = np.asarray(
        treatment_values,
        dtype=float,
    )

    control_values = np.asarray(
        control_values,
        dtype=float,
    )

    if iterations <= 0:
        raise ValueError(
            "bootstrap iterations must be positive."
        )

    if batch_size <= 0:
        raise ValueError(
            "bootstrap batch size must be positive."
        )

    n_t = len(treatment_values)
    n_c = len(control_values)

    bootstrap_effects = np.empty(
        iterations,
        dtype=float,
    )

    completed = 0

    while completed < iterations:
        current_batch = min(
            batch_size,
            iterations - completed,
        )

        treatment_indices = rng.integers(
            0,
            n_t,
            size=(current_batch, n_t),
        )

        control_indices = rng.integers(
            0,
            n_c,
            size=(current_batch, n_c),
        )

        treatment_means = treatment_values[
            treatment_indices
        ].mean(axis=1)

        control_means = control_values[
            control_indices
        ].mean(axis=1)

        bootstrap_effects[
            completed : completed + current_batch
        ] = treatment_means - control_means

        completed += current_batch

    lower = float(
        np.quantile(
            bootstrap_effects,
            alpha / 2.0,
        )
    )

    upper = float(
        np.quantile(
            bootstrap_effects,
            1.0 - alpha / 2.0,
        )
    )

    return lower, upper


def holm_adjust(
    p_values: np.ndarray,
) -> np.ndarray:
    """
    Holm step-down family-wise error rate correction.

    No external multiple-testing dependency is required.
    """
    p_values = np.asarray(
        p_values,
        dtype=float,
    )

    m = len(p_values)

    order = np.argsort(p_values)

    sorted_p = p_values[order]

    adjusted_sorted = np.empty(
        m,
        dtype=float,
    )

    running_max = 0.0

    for rank, p_value in enumerate(
        sorted_p,
        start=1,
    ):
        multiplier = m - rank + 1

        adjusted = min(
            1.0,
            multiplier * p_value,
        )

        running_max = max(
            running_max,
            adjusted,
        )

        adjusted_sorted[
            rank - 1
        ] = running_max

    adjusted = np.empty(
        m,
        dtype=float,
    )

    adjusted[order] = adjusted_sorted

    return adjusted


def estimate_all_effects(
    df: pd.DataFrame,
    alpha: float,
    bootstrap_iterations: int,
    bootstrap_batch_size: int,
    seed: int,
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []

    rng = np.random.default_rng(
        seed
    )

    control_df = df[
        df["treatment_group"] == CONTROL
    ]

    for treatment in TREATMENTS:
        treatment_df = df[
            df["treatment_group"] == treatment
        ]

        for outcome in BINARY_OUTCOMES:
            estimate = estimate_binary_effect(
                treatment_values=treatment_df[
                    outcome
                ].to_numpy(),
                control_values=control_df[
                    outcome
                ].to_numpy(),
                alpha=alpha,
            )

            records.append(
                {
                    "comparison": f"{treatment}_vs_control",
                    "treatment": treatment,
                    "control": CONTROL,
                    "outcome": outcome,
                    "outcome_type": "binary",
                    **estimate,
                    "bootstrap_ci_low": np.nan,
                    "bootstrap_ci_high": np.nan,
                }
            )

        for outcome in CONTINUOUS_OUTCOMES:
            treatment_values = treatment_df[
                outcome
            ].to_numpy()

            control_values = control_df[
                outcome
            ].to_numpy()

            estimate = estimate_continuous_effect(
                treatment_values=treatment_values,
                control_values=control_values,
                alpha=alpha,
            )

            bootstrap_low, bootstrap_high = (
                bootstrap_mean_difference(
                    treatment_values=treatment_values,
                    control_values=control_values,
                    iterations=bootstrap_iterations,
                    batch_size=bootstrap_batch_size,
                    alpha=alpha,
                    rng=rng,
                )
            )

            records.append(
                {
                    "comparison": f"{treatment}_vs_control",
                    "treatment": treatment,
                    "control": CONTROL,
                    "outcome": outcome,
                    "outcome_type": "continuous",
                    **estimate,
                    "bootstrap_ci_low": bootstrap_low,
                    "bootstrap_ci_high": bootstrap_high,
                }
            )

    results = pd.DataFrame(
        records
    )

    results["p_value_holm"] = holm_adjust(
        results["p_value"].to_numpy()
    )

    results["significant_raw"] = (
        results["p_value"] < alpha
    )

    results["significant_holm"] = (
        results["p_value_holm"] < alpha
    )

    return results


def build_summary(
    results: pd.DataFrame,
    source_table: str,
    alpha: float,
    bootstrap_iterations: int,
    seed: int,
) -> dict[str, Any]:
    effects: list[dict[str, Any]] = []

    for row in results.to_dict(
        orient="records"
    ):
        cleaned: dict[str, Any] = {}

        for key, value in row.items():
            if isinstance(
                value,
                (np.floating, np.integer),
            ):
                value = value.item()

            if isinstance(value, float) and np.isnan(value):
                value = None

            cleaned[key] = value

        effects.append(cleaned)

    return {
        "source_table": source_table,
        "estimand": "intention-to-treat effect",
        "control_group": CONTROL,
        "treatment_groups": TREATMENTS,
        "outcomes": ALL_OUTCOMES,
        "alpha": alpha,
        "multiple_testing_correction": (
            "Holm correction across all six treatment-outcome tests"
        ),
        "spend_bootstrap_iterations": bootstrap_iterations,
        "random_seed": seed,
        "effects": effects,
        "interpretation": (
            "Treatment effects are estimated relative to the randomized "
            "control population. Spend is measured per randomized user, "
            "including zero-spend users."
        ),
    }


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
        output_dir / "ate_estimates.csv",
        index=False,
    )

    with (
        output_dir / "ate_summary.json"
    ).open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            summary,
            file,
            indent=2,
            ensure_ascii=False,
        )


def print_report(
    results: pd.DataFrame,
    alpha: float,
) -> None:
    display = results.copy()

    display["control_mean"] = display[
        "control_mean"
    ].map(
        lambda x: f"{x:.6f}"
    )

    display["treatment_mean"] = display[
        "treatment_mean"
    ].map(
        lambda x: f"{x:.6f}"
    )

    display["ate"] = display[
        "ate"
    ].map(
        lambda x: f"{x:.6f}"
    )

    display["relative_lift"] = display[
        "relative_lift"
    ].map(
        lambda x: (
            f"{100 * x:.2f}%"
            if pd.notna(x)
            else "NA"
        )
    )

    display["ci"] = results.apply(
        lambda row: (
            f"[{row['ci_low']:.6f}, "
            f"{row['ci_high']:.6f}]"
        ),
        axis=1,
    )

    display["p_value"] = results[
        "p_value"
    ].map(
        lambda x: f"{x:.6g}"
    )

    display["p_value_holm"] = results[
        "p_value_holm"
    ].map(
        lambda x: f"{x:.6g}"
    )

    columns = [
        "comparison",
        "outcome",
        "control_mean",
        "treatment_mean",
        "ate",
        "relative_lift",
        "ci",
        "p_value",
        "p_value_holm",
        "significant_holm",
    ]

    print(
        "\n=== Intention-to-Treat Estimates ==="
    )

    print(
        display[
            columns
        ].to_string(
            index=False
        )
    )

    spend_rows = results[
        results["outcome"] == "spend"
    ]

    print(
        "\n=== Spend Bootstrap Robustness Check ==="
    )

    for _, row in spend_rows.iterrows():
        print(
            f"{row['comparison']}: "
            f"ATE={row['ate']:.6f}, "
            f"bootstrap "
            f"{100 * (1 - alpha):.1f}% CI="
            f"[{row['bootstrap_ci_low']:.6f}, "
            f"{row['bootstrap_ci_high']:.6f}]"
        )

    print(
        "\nInference notes:"
    )

    print(
        "- Binary outcomes use difference-in-proportions inference."
    )

    print(
        "- Spend uses Welch inference plus a percentile bootstrap CI."
    )

    print(
        "- Holm adjustment controls family-wise error across the "
        "six pre-specified treatment-outcome comparisons."
    )

    print(
        "- Estimates are ITT effects relative to control."
    )


def main() -> None:
    args = parse_args()

    table_id = resolve_table_id(
        project=args.project,
        table=args.table,
    )

    client = bigquery.Client(
        project=args.project,
    )

    print(
        f"Source table: `{table_id}`"
    )

    df = load_experiment_data(
        client=client,
        table_id=table_id,
    )

    validate_data(
        df
    )

    print(
        f"Loaded experiment rows: {len(df)}"
    )

    results = estimate_all_effects(
        df=df,
        alpha=args.alpha,
        bootstrap_iterations=args.bootstrap_iterations,
        bootstrap_batch_size=args.bootstrap_batch_size,
        seed=args.seed,
    )

    summary = build_summary(
        results=results,
        source_table=table_id,
        alpha=args.alpha,
        bootstrap_iterations=args.bootstrap_iterations,
        seed=args.seed,
    )

    save_outputs(
        results=results,
        summary=summary,
        output_dir=Path(
            args.output_dir
        ),
    )

    print_report(
        results=results,
        alpha=args.alpha,
    )


if __name__ == "__main__":
    main()