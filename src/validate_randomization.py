from __future__ import annotations

import argparse
import json
import os
import re
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from google.cloud import bigquery
from scipy.stats import chisquare


TREATMENT_COLUMN = "segment"

TREATMENT_ORDER = [
    "No E-Mail",
    "Mens E-Mail",
    "Womens E-Mail",
]

# Pre-treatment covariates only.
# visit / conversion / spend must never be used here.
NUMERIC_COVARIATES = [
    "recency",
    "history",
    "mens",
    "womens",
    "newbie",
]

CATEGORICAL_COVARIATES = [
    "history_segment",
    "zip_code",
    "channel",
]

POST_TREATMENT_OUTCOMES = {
    "visit",
    "conversion",
    "spend",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate Hillstrom treatment assignment using sample-ratio "
            "checks and pre-treatment covariate balance."
        )
    )

    parser.add_argument(
        "--project",
        default=os.getenv("GOOGLE_CLOUD_PROJECT"),
        help="Google Cloud project ID.",
    )

    parser.add_argument(
        "--table",
        default="ceus.hillstrom_raw",
        help=(
            "BigQuery source table. "
            "Use dataset.table with --project, or project.dataset.table."
        ),
    )

    parser.add_argument(
        "--output-dir",
        default="data/processed",
        help="Directory for validation outputs.",
    )

    parser.add_argument(
        "--smd-threshold",
        type=float,
        default=0.10,
        help="Absolute SMD threshold used to flag material imbalance.",
    )

    parser.add_argument(
        "--srm-alpha",
        type=float,
        default=0.01,
        help="Significance threshold for the sample-ratio mismatch check.",
    )

    parser.add_argument(
        "--expected-ratios",
        nargs=3,
        type=float,
        default=[1.0, 1.0, 1.0],
        metavar=("CONTROL", "MENS", "WOMENS"),
        help="Expected allocation ratios for the three treatment groups.",
    )

    return parser.parse_args()


def resolve_table_id(project: str | None, table: str) -> str:
    """
    Resolve dataset.table or project.dataset.table into a fully-qualified
    BigQuery table ID.
    """
    if not re.fullmatch(r"[A-Za-z0-9_\-]+(?:\.[A-Za-z0-9_\-]+){1,2}", table):
        raise ValueError(
            "Invalid table identifier. Expected dataset.table "
            "or project.dataset.table."
        )

    parts = table.split(".")

    if len(parts) == 3:
        return table

    if len(parts) == 2:
        if not project:
            raise ValueError(
                "--project is required when --table is given as dataset.table."
            )
        return f"{project}.{table}"

    raise ValueError(f"Unsupported table identifier: {table}")


def validate_configuration() -> None:
    """
    Guard against accidental leakage of post-treatment variables into
    randomization validation.
    """
    covariates = set(NUMERIC_COVARIATES + CATEGORICAL_COVARIATES)

    leakage = covariates & POST_TREATMENT_OUTCOMES
    if leakage:
        raise ValueError(
            f"Post-treatment variables included in balance checks: {sorted(leakage)}"
        )

    if TREATMENT_COLUMN in covariates:
        raise ValueError("Treatment column cannot also be a covariate.")


def load_pre_treatment_data(
    client: bigquery.Client,
    table_id: str,
) -> pd.DataFrame:
    """
    Pull only treatment assignment and pre-treatment covariates.

    Post-treatment outcomes are deliberately excluded.
    """
    columns = [
        TREATMENT_COLUMN,
        *NUMERIC_COVARIATES,
        *CATEGORICAL_COVARIATES,
    ]

    select_clause = ",\n        ".join(f"`{column}`" for column in columns)

    query = f"""
    SELECT
        {select_clause}
    FROM `{table_id}`
    """

    rows = client.query(query).result()

    records = [dict(row.items()) for row in rows]

    if not records:
        raise ValueError(f"No rows returned from `{table_id}`.")

    return pd.DataFrame.from_records(records)


def validate_treatment_domain(df: pd.DataFrame) -> None:
    observed = set(df[TREATMENT_COLUMN].dropna().unique())
    expected = set(TREATMENT_ORDER)

    unexpected = observed - expected
    missing = expected - observed

    if unexpected:
        raise ValueError(
            f"Unexpected treatment values found: {sorted(unexpected)}"
        )

    if missing:
        raise ValueError(
            f"Expected treatment groups missing: {sorted(missing)}"
        )

    if df[TREATMENT_COLUMN].isna().any():
        raise ValueError("Treatment assignment contains NULL values.")


def calculate_treatment_counts(df: pd.DataFrame) -> pd.DataFrame:
    counts = (
        df[TREATMENT_COLUMN]
        .value_counts()
        .reindex(TREATMENT_ORDER)
        .rename_axis("segment")
        .reset_index(name="n")
    )

    counts["share"] = counts["n"] / counts["n"].sum()

    return counts


def run_sample_ratio_check(
    treatment_counts: pd.DataFrame,
    expected_ratios: list[float],
    alpha: float,
) -> dict:
    """
    Pearson chi-square goodness-of-fit test.

    This only tests whether observed allocation counts materially deviate
    from the specified allocation ratio.

    Passing this test does not prove successful randomization.
    """
    observed = treatment_counts["n"].to_numpy(dtype=float)

    ratios = np.asarray(expected_ratios, dtype=float)

    if np.any(ratios <= 0):
        raise ValueError("Expected treatment ratios must all be positive.")

    probabilities = ratios / ratios.sum()
    expected = observed.sum() * probabilities

    statistic, p_value = chisquare(
        f_obs=observed,
        f_exp=expected,
    )

    return {
        "observed_counts": {
            row["segment"]: int(row["n"])
            for _, row in treatment_counts.iterrows()
        },
        "expected_counts": {
            segment: float(count)
            for segment, count in zip(TREATMENT_ORDER, expected)
        },
        "chi_square_statistic": float(statistic),
        "p_value": float(p_value),
        "alpha": float(alpha),
        "sample_ratio_mismatch_flag": bool(p_value < alpha),
    }


def standardized_mean_difference(
    group_a: pd.Series,
    group_b: pd.Series,
) -> tuple[float, float, float, float, float]:
    """
    Calculate pairwise standardized mean difference:

        SMD = (mean_A - mean_B) /
              sqrt((var_A + var_B) / 2)

    Returns:
        mean_a, mean_b, sd_a, sd_b, smd
    """
    a = pd.to_numeric(group_a, errors="coerce").dropna().astype(float)
    b = pd.to_numeric(group_b, errors="coerce").dropna().astype(float)

    if a.empty or b.empty:
        return np.nan, np.nan, np.nan, np.nan, np.nan

    mean_a = float(a.mean())
    mean_b = float(b.mean())

    sd_a = float(a.std(ddof=1))
    sd_b = float(b.std(ddof=1))

    pooled_variance = (sd_a**2 + sd_b**2) / 2.0

    if np.isclose(pooled_variance, 0.0):
        if np.isclose(mean_a, mean_b):
            smd = 0.0
        else:
            smd = np.inf
    else:
        smd = (mean_a - mean_b) / np.sqrt(pooled_variance)

    return mean_a, mean_b, sd_a, sd_b, float(smd)


def numeric_balance(
    df: pd.DataFrame,
    threshold: float,
) -> pd.DataFrame:
    records: list[dict] = []

    for covariate in NUMERIC_COVARIATES:
        for group_a, group_b in combinations(TREATMENT_ORDER, 2):
            values_a = df.loc[
                df[TREATMENT_COLUMN] == group_a,
                covariate,
            ]

            values_b = df.loc[
                df[TREATMENT_COLUMN] == group_b,
                covariate,
            ]

            mean_a, mean_b, sd_a, sd_b, smd = standardized_mean_difference(
                values_a,
                values_b,
            )

            records.append(
                {
                    "covariate": covariate,
                    "covariate_type": "numeric_or_binary",
                    "level": None,
                    "group_a": group_a,
                    "group_b": group_b,
                    "value_a": mean_a,
                    "value_b": mean_b,
                    "sd_a": sd_a,
                    "sd_b": sd_b,
                    "smd": smd,
                    "abs_smd": abs(smd),
                    "imbalance_flag": abs(smd) >= threshold,
                }
            )

    return pd.DataFrame(records)


def categorical_balance(
    df: pd.DataFrame,
    threshold: float,
) -> pd.DataFrame:
    """
    For categorical covariates, convert each category level into a binary
    indicator and calculate pairwise SMD on the level proportions.
    """
    records: list[dict] = []

    for covariate in CATEGORICAL_COVARIATES:
        values = df[covariate].astype("string").fillna("<MISSING>")

        levels = sorted(values.unique().tolist())

        for level in levels:
            indicator = (values == level).astype(float)

            for group_a, group_b in combinations(TREATMENT_ORDER, 2):
                mask_a = df[TREATMENT_COLUMN] == group_a
                mask_b = df[TREATMENT_COLUMN] == group_b

                indicator_a = indicator.loc[mask_a]
                indicator_b = indicator.loc[mask_b]

                (
                    proportion_a,
                    proportion_b,
                    sd_a,
                    sd_b,
                    smd,
                ) = standardized_mean_difference(
                    indicator_a,
                    indicator_b,
                )

                records.append(
                    {
                        "covariate": covariate,
                        "covariate_type": "categorical_level",
                        "level": level,
                        "group_a": group_a,
                        "group_b": group_b,
                        "value_a": proportion_a,
                        "value_b": proportion_b,
                        "sd_a": sd_a,
                        "sd_b": sd_b,
                        "smd": smd,
                        "abs_smd": abs(smd),
                        "imbalance_flag": abs(smd) >= threshold,
                    }
                )

    return pd.DataFrame(records)


def summarize_covariate_balance(
    balance: pd.DataFrame,
    threshold: float,
) -> pd.DataFrame:
    """
    Reduce level-wise and pairwise results to one row per covariate using
    the maximum absolute SMD observed.
    """
    summary = (
        balance.groupby("covariate", as_index=False)
        .agg(
            max_abs_smd=("abs_smd", "max"),
            mean_abs_smd=("abs_smd", "mean"),
            comparisons=("abs_smd", "size"),
        )
        .sort_values(
            "max_abs_smd",
            ascending=False,
        )
    )

    summary["imbalance_flag"] = summary["max_abs_smd"] >= threshold

    return summary


def save_outputs(
    output_dir: Path,
    treatment_counts: pd.DataFrame,
    balance: pd.DataFrame,
    covariate_summary: pd.DataFrame,
    validation_summary: dict,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    treatment_counts.to_csv(
        output_dir / "randomization_treatment_counts.csv",
        index=False,
    )

    balance.to_csv(
        output_dir / "randomization_pairwise_balance.csv",
        index=False,
    )

    covariate_summary.to_csv(
        output_dir / "randomization_covariate_summary.csv",
        index=False,
    )

    with (
        output_dir / "randomization_validation_summary.json"
    ).open("w", encoding="utf-8") as f:
        json.dump(
            validation_summary,
            f,
            indent=2,
            ensure_ascii=False,
        )


def print_report(
    treatment_counts: pd.DataFrame,
    srm_result: dict,
    covariate_summary: pd.DataFrame,
    threshold: float,
) -> None:
    print("\n=== Treatment counts ===")
    print(treatment_counts.to_string(index=False))

    print("\n=== Sample Ratio Check ===")
    print(
        f"chi-square = "
        f"{srm_result['chi_square_statistic']:.6f}"
    )
    print(f"p-value    = {srm_result['p_value']:.6g}")
    print(
        f"SRM flag   = "
        f"{srm_result['sample_ratio_mismatch_flag']}"
    )

    print("\n=== Covariate Balance ===")
    print(
        covariate_summary[
            [
                "covariate",
                "max_abs_smd",
                "mean_abs_smd",
                "imbalance_flag",
            ]
        ].to_string(
            index=False,
            float_format=lambda x: f"{x:.4f}",
        )
    )

    max_abs_smd = float(
        covariate_summary["max_abs_smd"].max()
    )

    imbalance_count = int(
        covariate_summary["imbalance_flag"].sum()
    )

    print("\n=== Mechanical validation summary ===")

    print(
        f"Maximum absolute SMD: "
        f"{max_abs_smd:.4f}"
    )

    print(
        f"Covariates with |SMD| >= {threshold:.3f}: "
        f"{imbalance_count}"
    )

    if (
        not srm_result["sample_ratio_mismatch_flag"]
        and imbalance_count == 0
    ):
        print(
            "Result: no material allocation or pre-treatment "
            "covariate imbalance detected under the configured thresholds."
        )
    else:
        print(
            "Result: allocation and/or covariate imbalance requires review."
        )

    print(
        "\nImportant: this is a diagnostic check, not proof that "
        "randomization was successfully implemented."
    )


def main() -> None:
    args = parse_args()

    validate_configuration()

    table_id = resolve_table_id(
        project=args.project,
        table=args.table,
    )

    client = bigquery.Client(
        project=args.project,
    )

    print(f"Source table: `{table_id}`")

    df = load_pre_treatment_data(
        client=client,
        table_id=table_id,
    )

    validate_treatment_domain(df)

    treatment_counts = calculate_treatment_counts(df)

    srm_result = run_sample_ratio_check(
        treatment_counts=treatment_counts,
        expected_ratios=args.expected_ratios,
        alpha=args.srm_alpha,
    )

    numeric_results = numeric_balance(
        df=df,
        threshold=args.smd_threshold,
    )

    categorical_results = categorical_balance(
        df=df,
        threshold=args.smd_threshold,
    )

    balance = pd.concat(
        [
            numeric_results,
            categorical_results,
        ],
        ignore_index=True,
    )

    covariate_summary = summarize_covariate_balance(
        balance=balance,
        threshold=args.smd_threshold,
    )

    max_abs_smd = float(
        covariate_summary["max_abs_smd"].max()
    )

    validation_summary = {
        "source_table": table_id,
        "n_rows": int(len(df)),
        "treatment_groups": TREATMENT_ORDER,
        "expected_ratios": args.expected_ratios,
        "srm": srm_result,
        "smd_threshold": args.smd_threshold,
        "max_abs_smd": max_abs_smd,
        "imbalanced_covariates": (
            covariate_summary.loc[
                covariate_summary["imbalance_flag"],
                "covariate",
            ]
            .tolist()
        ),
        "interpretation": (
            "Diagnostic only. Passing these checks does not prove "
            "successful randomization."
        ),
    }

    save_outputs(
        output_dir=Path(args.output_dir),
        treatment_counts=treatment_counts,
        balance=balance,
        covariate_summary=covariate_summary,
        validation_summary=validation_summary,
    )

    print_report(
        treatment_counts=treatment_counts,
        srm_result=srm_result,
        covariate_summary=covariate_summary,
        threshold=args.smd_threshold,
    )


if __name__ == "__main__":
    main()