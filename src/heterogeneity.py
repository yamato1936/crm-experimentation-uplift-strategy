from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from google.cloud import bigquery
from scipy import stats


CONTROL = "control"

TREATMENTS = [
    "mens_email",
    "womens_email",
]

OUTCOMES = [
    "visit",
    "conversion",
    "spend",
]

BINARY_OUTCOMES = {
    "visit",
    "conversion",
}

# ------------------------------------------------------------
# targeted_followup heterogeneity hypotheses
#
# These are deliberately limited rather than testing every
# possible segment discovered in 03_segment_analysis.sql.
# ------------------------------------------------------------
TARGETED_FOLLOWUP_BINARY_INTERACTIONS = [
    {
        "treatment": "womens_email",
        "moderator": "womens",
        "hypothesis": (
            "Women's Email effect differs by prior women's merchandise purchase."
        ),
    },
    {
        "treatment": "mens_email",
        "moderator": "mens",
        "hypothesis": (
            "Men's Email effect differs by prior men's merchandise purchase."
        ),
    },
]

# Channel is treated as an exploratory categorical moderator.
EXPLORATORY_CATEGORICAL_MODERATORS = [
    "channel",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Estimate heterogeneous treatment effects in the Hillstrom "
            "randomized email experiment using treatment-moderator interactions."
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
            "Use dataset.table with --project or project.dataset.table."
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
        help="Two-sided significance level.",
    )

    parser.add_argument(
        "--min-cell-n",
        type=int,
        default=100,
        help=(
            "Diagnostic threshold for small treatment × moderator cells. "
            "Cells are flagged, not automatically dropped."
        ),
    )

    return parser.parse_args()


def resolve_table_id(project: str | None,table: str) -> str:
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

    raise ValueError(
        f"Invalid table identifier: {table}"
    )


def load_data(client: bigquery.Client, table_id: str) -> pd.DataFrame:
    """
    Load treatment assignment, pre-treatment moderators and outcomes.

    Moderators:
        mens
        womens
        channel

    Outcomes are post-treatment and are used only as dependent variables.
    """
    query = f"""
    SELECT
        treatment_group,

        -- Pre-treatment moderators
        mens,
        womens,
        channel,

        -- Post-treatment outcomes
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

    for column in [
        "mens",
        "womens",
        "visit",
        "conversion",
        "spend",
    ]:
        df[column] = pd.to_numeric(
            df[column],
            errors="raise",
        )

    return df


def validate_data(df: pd.DataFrame) -> None:
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

    for moderator in [
        "mens",
        "womens",
    ]:
        values = set(
            df[moderator]
            .dropna()
            .unique()
        )

        if not values.issubset(
            {0, 1}
        ):
            raise ValueError(
                f"{moderator} contains invalid values: "
                f"{sorted(values)}"
            )

        if df[moderator].isna().any():
            raise ValueError(
                f"{moderator} contains missing values."
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

    if df["spend"].isna().any():
        raise ValueError(
            "spend contains missing values."
        )

    if (
        df["spend"] < 0
    ).any():
        raise ValueError(
            "spend contains negative values."
        )

    if df["channel"].isna().any():
        raise ValueError(
            "channel contains missing values."
        )


def holm_adjust(p_values: np.ndarray) -> np.ndarray:
    """
    Holm step-down family-wise error correction.
    """
    p_values = np.asarray(
        p_values,
        dtype=float,
    )

    m = len(p_values)

    if m == 0:
        return np.array(
            [],
            dtype=float,
        )

    order = np.argsort(
        p_values
    )

    sorted_p = p_values[
        order
    ]

    adjusted_sorted = np.empty(
        m,
        dtype=float,
    )

    running_max = 0.0

    for rank, p_value in enumerate(
        sorted_p,
        start=1,
    ):
        multiplier = (
            m - rank + 1
        )

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

    adjusted[
        order
    ] = adjusted_sorted

    return adjusted


def linear_combination(result: Any,weights: dict[str, float],alpha: float) -> dict[str, float]:
    """
    Estimate an arbitrary linear combination of regression coefficients.

    Used to derive treatment effects within moderator strata.
    """
    parameter_names = list(
        result.params.index
    )

    vector = np.zeros(
        len(parameter_names),
        dtype=float,
    )

    for parameter, weight in weights.items():
        if parameter not in parameter_names:
            raise ValueError(
                f"Parameter `{parameter}` not found in model."
            )

        vector[
            parameter_names.index(
                parameter
            )
        ] = weight

    params = result.params.to_numpy(
        dtype=float
    )

    covariance = result.cov_params().to_numpy(
        dtype=float
    )

    estimate = float(
        vector @ params
    )

    variance = float(
        vector
        @ covariance
        @ vector
    )

    variance = max(
        variance,
        0.0,
    )

    standard_error = float(
        np.sqrt(
            variance
        )
    )

    if standard_error == 0.0:
        test_statistic = (
            0.0
            if np.isclose(
                estimate,
                0.0,
            )
            else np.inf
        )
    else:
        test_statistic = (
            estimate
            / standard_error
        )

    p_value = float(
        2.0
        * stats.norm.sf(
            abs(
                test_statistic
            )
        )
    )

    critical_value = float(
        stats.norm.ppf(
            1.0
            - alpha / 2.0
        )
    )

    ci_low = (
        estimate
        - critical_value
        * standard_error
    )

    ci_high = (
        estimate
        + critical_value
        * standard_error
    )

    return {
        "estimate": estimate,
        "standard_error": standard_error,
        "ci_low": float(
            ci_low
        ),
        "ci_high": float(
            ci_high
        ),
        "test_statistic": float(
            test_statistic
        ),
        "p_value": p_value,
    }


def binary_cell_counts(
    data: pd.DataFrame,
    moderator: str,
) -> pd.DataFrame:
    return (
        data.groupby(
            [
                "treatment_indicator",
                moderator,
            ],
            as_index=False,
        )
        .size()
        .rename(
            columns={
                "size": "cell_n",
            }
        )
    )


def estimate_binary_moderator_interaction(
    df: pd.DataFrame,
    treatment: str,
    moderator: str,
    outcome: str,
    alpha: float,
    min_cell_n: int,
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
]:
    """
    Estimate:

        Y = beta0
            + beta1 * T
            + beta2 * X
            + beta3 * T*X
            + error

    where:
        T = 1 treatment, 0 control
        X = binary pre-treatment moderator

    beta3 is the difference in treatment effects:

        tau(X=1) - tau(X=0)

    For binary outcomes this is a Linear Probability Model.

    HC3 heteroskedasticity-robust standard errors are used for all
    outcomes so the interaction coefficient remains directly
    interpretable on the original outcome scale.
    """
    data = df[
        df["treatment_group"].isin(
            [
                CONTROL,
                treatment,
            ]
        )
    ].copy()

    data["treatment_indicator"] = (
        data["treatment_group"]
        == treatment
    ).astype(
        float
    )

    data["moderator_value"] = (
        data[moderator]
        .astype(
            float
        )
    )

    cell_counts = binary_cell_counts(
        data=data,
        moderator=moderator,
    )

    if len(
        cell_counts
    ) != 4:
        raise ValueError(
            f"Incomplete 2x2 treatment × {moderator} cells "
            f"for {treatment}."
        )

    min_observed_cell_n = int(
        cell_counts[
            "cell_n"
        ].min()
    )

    formula = (
        f"{outcome} ~ "
        "treatment_indicator "
        "+ moderator_value "
        "+ treatment_indicator:moderator_value"
    )

    model = smf.ols(
        formula=formula,
        data=data,
    )

    result = model.fit(
        cov_type="HC3"
    )

    interaction_name = (
        "treatment_indicator:moderator_value"
    )

    interaction = linear_combination(
        result=result,
        weights={
            interaction_name: 1.0,
        },
        alpha=alpha,
    )

    # Treatment effect when moderator = 0:
    #
    #   tau_0 = beta_treatment
    tau_0 = linear_combination(
        result=result,
        weights={
            "treatment_indicator": 1.0,
        },
        alpha=alpha,
    )

    # Treatment effect when moderator = 1:
    #
    #   tau_1 = beta_treatment + beta_interaction
    tau_1 = linear_combination(
        result=result,
        weights={
            "treatment_indicator": 1.0,
            interaction_name: 1.0,
        },
        alpha=alpha,
    )

    interaction_record = {
        "analysis_family": (
            "targeted_followup_binary_interaction"
        ),
        "treatment": treatment,
        "control": CONTROL,
        "moderator": moderator,
        "outcome": outcome,
        "outcome_type": (
            "binary"
            if outcome in BINARY_OUTCOMES
            else "continuous"
        ),
        "n": int(
            len(
                data
            )
        ),
        "min_cell_n": (
            min_observed_cell_n
        ),
        "small_cell_flag": bool(
            min_observed_cell_n
            < min_cell_n
        ),
        "interaction_effect": interaction[
            "estimate"
        ],
        "interaction_se": interaction[
            "standard_error"
        ],
        "interaction_ci_low": interaction[
            "ci_low"
        ],
        "interaction_ci_high": interaction[
            "ci_high"
        ],
        "interaction_z": interaction[
            "test_statistic"
        ],
        "interaction_p_value": interaction[
            "p_value"
        ],
    }

    stratum_records = [
        {
            "treatment": treatment,
            "control": CONTROL,
            "moderator": moderator,
            "moderator_value": 0,
            "outcome": outcome,
            "n": int(
                len(
                    data
                )
            ),
            "treatment_effect": tau_0[
                "estimate"
            ],
            "standard_error": tau_0[
                "standard_error"
            ],
            "ci_low": tau_0[
                "ci_low"
            ],
            "ci_high": tau_0[
                "ci_high"
            ],
            "p_value": tau_0[
                "p_value"
            ],
        },
        {
            "treatment": treatment,
            "control": CONTROL,
            "moderator": moderator,
            "moderator_value": 1,
            "outcome": outcome,
            "n": int(
                len(
                    data
                )
            ),
            "treatment_effect": tau_1[
                "estimate"
            ],
            "standard_error": tau_1[
                "standard_error"
            ],
            "ci_low": tau_1[
                "ci_low"
            ],
            "ci_high": tau_1[
                "ci_high"
            ],
            "p_value": tau_1[
                "p_value"
            ],
        },
    ]

    return (
        interaction_record,
        stratum_records,
    )


def estimate_targeted_followup_interactions(
    df: pd.DataFrame,
    alpha: float,
    min_cell_n: int,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
]:
    interaction_records: list[
        dict[str, Any]
    ] = []

    stratum_records: list[
        dict[str, Any]
    ] = []

    for hypothesis in (
        TARGETED_FOLLOWUP_BINARY_INTERACTIONS
    ):
        treatment = hypothesis[
            "treatment"
        ]

        moderator = hypothesis[
            "moderator"
        ]

        for outcome in OUTCOMES:
            (
                interaction,
                strata,
            ) = (
                estimate_binary_moderator_interaction(
                    df=df,
                    treatment=treatment,
                    moderator=moderator,
                    outcome=outcome,
                    alpha=alpha,
                    min_cell_n=min_cell_n,
                )
            )

            interaction[
                "hypothesis"
            ] = hypothesis[
                "hypothesis"
            ]

            interaction_records.append(
                interaction
            )

            stratum_records.extend(
                strata
            )

    interactions = pd.DataFrame(
        interaction_records
    )

    strata = pd.DataFrame(
        stratum_records
    )

    # Holm correction across the six targeted follow-up interaction tests selected after descriptive subgroup review.
    #
    # 2 hypotheses × 3 outcomes.
    interactions[
        "interaction_p_value_holm"
    ] = holm_adjust(
        interactions[
            "interaction_p_value"
        ].to_numpy()
    )

    interactions[
        "significant_raw"
    ] = (
        interactions[
            "interaction_p_value"
        ]
        < alpha
    )

    interactions[
        "significant_holm"
    ] = (
        interactions[
            "interaction_p_value_holm"
        ]
        < alpha
    )

    return (
        interactions,
        strata,
    )


def categorical_cell_counts(
    data: pd.DataFrame,
    moderator: str,
) -> pd.DataFrame:
    return (
        data.groupby(
            [
                "treatment_indicator",
                moderator,
            ],
            as_index=False,
        )
        .size()
        .rename(
            columns={
                "size": "cell_n",
            }
        )
    )


def estimate_categorical_global_interaction(
    df: pd.DataFrame,
    treatment: str,
    moderator: str,
    outcome: str,
    min_cell_n: int,
) -> dict[str, Any]:
    """
    Fit:

        Y ~ Treatment * C(Moderator)

    and jointly test all Treatment × Moderator interaction terms.

    The global null is:

        treatment effect is equal across every moderator level.

    This avoids declaring heterogeneity based only on the largest
    observed subgroup estimate.
    """
    data = df[
        df["treatment_group"].isin(
            [
                CONTROL,
                treatment,
            ]
        )
    ].copy()

    data["treatment_indicator"] = (
        data["treatment_group"]
        == treatment
    ).astype(
        float
    )

    cell_counts = (
        categorical_cell_counts(
            data=data,
            moderator=moderator,
        )
    )

    min_observed_cell_n = int(
        cell_counts[
            "cell_n"
        ].min()
    )

    expected_cell_count = (
        2
        * data[
            moderator
        ].nunique()
    )

    incomplete_cells = (
        len(
            cell_counts
        )
        != expected_cell_count
    )

    formula = (
        f"{outcome} ~ "
        f"treatment_indicator * C({moderator})"
    )

    result = smf.ols(
        formula=formula,
        data=data,
    ).fit(
        cov_type="HC3"
    )

    parameter_names = list(
        result.params.index
    )

    interaction_names = [
        name
        for name in parameter_names
        if (
            ":"
            in name
            and "treatment_indicator"
            in name
            and f"C({moderator})"
            in name
        )
    ]

    if not interaction_names:
        raise ValueError(
            "No categorical interaction parameters found for "
            f"{treatment} × {moderator}."
        )

    restriction_matrix = np.zeros(
        (
            len(
                interaction_names
            ),
            len(
                parameter_names
            ),
        ),
        dtype=float,
    )

    for row_index, parameter in enumerate(
        interaction_names
    ):
        column_index = (
            parameter_names.index(
                parameter
            )
        )

        restriction_matrix[
            row_index,
            column_index,
        ] = 1.0

    wald_result = result.wald_test(
        restriction_matrix,
        use_f=False,
        scalar=True,
    )

    statistic = float(
        wald_result.statistic
    )

    p_value = float(
        wald_result.pvalue
    )

    return {
        "analysis_family": (
            "exploratory_categorical_global_interaction"
        ),
        "treatment": treatment,
        "control": CONTROL,
        "moderator": moderator,
        "outcome": outcome,
        "outcome_type": (
            "binary"
            if outcome in BINARY_OUTCOMES
            else "continuous"
        ),
        "n": int(
            len(
                data
            )
        ),
        "moderator_levels": int(
            data[
                moderator
            ].nunique()
        ),
        "interaction_constraints": len(
            interaction_names
        ),
        "wald_chi_square": statistic,
        "global_interaction_p_value": p_value,
        "min_cell_n": (
            min_observed_cell_n
        ),
        "small_cell_flag": bool(
            min_observed_cell_n
            < min_cell_n
        ),
        "incomplete_cell_flag": bool(
            incomplete_cells
        ),
    }


def estimate_exploratory_global_tests(
    df: pd.DataFrame,
    alpha: float,
    min_cell_n: int,
) -> pd.DataFrame:
    records: list[
        dict[str, Any]
    ] = []

    for moderator in (
        EXPLORATORY_CATEGORICAL_MODERATORS
    ):
        for treatment in TREATMENTS:
            for outcome in OUTCOMES:
                records.append(
                    estimate_categorical_global_interaction(
                        df=df,
                        treatment=treatment,
                        moderator=moderator,
                        outcome=outcome,
                        min_cell_n=min_cell_n,
                    )
                )

    results = pd.DataFrame(
        records
    )

    results[
        "global_interaction_p_value_holm"
    ] = holm_adjust(
        results[
            "global_interaction_p_value"
        ].to_numpy()
    )

    results[
        "significant_raw"
    ] = (
        results[
            "global_interaction_p_value"
        ]
        < alpha
    )

    results[
        "significant_holm"
    ] = (
        results[
            "global_interaction_p_value_holm"
        ]
        < alpha
    )

    return results


def build_summary(
    source_table: str,
    alpha: float,
    targeted_followup: pd.DataFrame,
    exploratory: pd.DataFrame,
) -> dict[str, Any]:
    significant_targeted_followup = (
        targeted_followup.loc[
            targeted_followup[
                "significant_holm"
            ],
            [
                "treatment",
                "moderator",
                "outcome",
                "interaction_effect",
                "interaction_ci_low",
                "interaction_ci_high",
                "interaction_p_value_holm",
            ],
        ]
        .to_dict(
            orient="records"
        )
    )

    significant_exploratory = (
        exploratory.loc[
            exploratory[
                "significant_holm"
            ],
            [
                "treatment",
                "moderator",
                "outcome",
                "wald_chi_square",
                "global_interaction_p_value_holm",
            ],
        ]
        .to_dict(
            orient="records"
        )
    )

    return {
        "source_table": source_table,
        "estimand": (
            "difference in treatment effects across pre-treatment moderators"
        ),
        "alpha": alpha,
        "model": (
            "OLS interaction model with HC3 heteroskedasticity-robust "
            "standard errors"
        ),
        "binary_outcome_interpretation": (
            "Linear probability model; interaction coefficients are "
            "differences in treatment effects on the probability scale."
        ),
        "targeted_followup_hypotheses": (
            TARGETED_FOLLOWUP_BINARY_INTERACTIONS
        ),
        "targeted_followup_multiple_testing": (
            "Holm correction across 6 targeted follow-up interaction tests: "
            "2 moderator-treatment hypotheses x 3 outcomes. These hypotheses "
            "were selected after descriptive subgroup review, so Holm adjustment "
            "controls multiplicity within this follow-up family but does not "
            "remove post-selection bias."
        ),
        "exploratory_categorical_moderators": (
            EXPLORATORY_CATEGORICAL_MODERATORS
        ),
        "exploratory_multiple_testing": (
            "Holm correction applied separately across categorical "
            "global interaction tests."
        ),
        "significant_targeted_followup_interactions": (
            significant_targeted_followup
        ),
        "significant_exploratory_global_interactions": (
            significant_exploratory
        ),
        "interpretation_guardrail": (
            "A subgroup treatment estimate is not evidence of "
            "heterogeneity by itself. Heterogeneity requires direct "
            "evidence that treatment effects differ across moderator levels."
        ),
    }


def save_outputs(
    output_dir: Path,
    targeted_followup: pd.DataFrame,
    stratum_effects: pd.DataFrame,
    exploratory: pd.DataFrame,
    summary: dict[str, Any],
) -> None:
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    targeted_followup.to_csv(
        output_dir
        / "heterogeneity_targeted_followup_interactions.csv",
        index=False,
    )

    stratum_effects.to_csv(
        output_dir
        / "heterogeneity_stratum_effects.csv",
        index=False,
    )

    exploratory.to_csv(
        output_dir
        / "heterogeneity_channel_global_tests.csv",
        index=False,
    )

    with (
        output_dir
        / "heterogeneity_summary.json"
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


def print_targeted_followup_report(
    results: pd.DataFrame,
) -> None:
    print(
        "\n=== targeted_followup Treatment × Moderator Interactions ==="
    )

    display = results[
        [
            "treatment",
            "moderator",
            "outcome",
            "interaction_effect",
            "interaction_ci_low",
            "interaction_ci_high",
            "interaction_p_value",
            "interaction_p_value_holm",
            "significant_holm",
        ]
    ].copy()

    for column in [
        "interaction_effect",
        "interaction_ci_low",
        "interaction_ci_high",
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
        "interaction_p_value"
    ] = display[
        "interaction_p_value"
    ].map(
        lambda value: (
            f"{value:.6g}"
        )
    )

    display[
        "interaction_p_value_holm"
    ] = display[
        "interaction_p_value_holm"
    ].map(
        lambda value: (
            f"{value:.6g}"
        )
    )

    print(
        display.to_string(
            index=False
        )
    )


def print_stratum_report(strata: pd.DataFrame,) -> None:
    print("\n=== Treatment Effects Within Moderator Strata ===")

    display = strata[
        [
            "treatment",
            "moderator",
            "moderator_value",
            "outcome",
            "treatment_effect",
            "ci_low",
            "ci_high",
        ]
    ].copy()

    for column in [
        "treatment_effect",
        "ci_low",
        "ci_high",
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


def print_exploratory_report(
    results: pd.DataFrame,
) -> None:
    print(
        "\n=== Exploratory Global Categorical Interactions ==="
    )

    display = results[
        [
            "treatment",
            "moderator",
            "outcome",
            "wald_chi_square",
            "interaction_constraints",
            "global_interaction_p_value",
            "global_interaction_p_value_holm",
            "significant_holm",
        ]
    ].copy()

    display[
        "wald_chi_square"
    ] = display[
        "wald_chi_square"
    ].map(
        lambda value: (
            f"{value:.6f}"
        )
    )

    display[
        "global_interaction_p_value"
    ] = display[
        "global_interaction_p_value"
    ].map(
        lambda value: (
            f"{value:.6g}"
        )
    )

    display[
        "global_interaction_p_value_holm"
    ] = display[
        "global_interaction_p_value_holm"
    ].map(
        lambda value: (
            f"{value:.6g}"
        )
    )

    print(
        display.to_string(
            index=False
        )
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

    (
        targeted_followup,
        stratum_effects,
    ) = estimate_targeted_followup_interactions(
        df=df,
        alpha=args.alpha,
        min_cell_n=args.min_cell_n,
    )

    exploratory = (
        estimate_exploratory_global_tests(
            df=df,
            alpha=args.alpha,
            min_cell_n=args.min_cell_n,
        )
    )

    summary = build_summary(
        source_table=table_id,
        alpha=args.alpha,
        targeted_followup=targeted_followup,
        exploratory=exploratory,
    )

    save_outputs(
        output_dir=Path(
            args.output_dir
        ),
        targeted_followup=targeted_followup,
        stratum_effects=stratum_effects,
        exploratory=exploratory,
        summary=summary,
    )

    print_targeted_followup_report(
        targeted_followup
    )

    print_stratum_report(
        stratum_effects
    )

    print_exploratory_report(
        exploratory
    )

    print(
        "\nInterpretation:"
    )

    print(
        "- interaction_effect > 0 means the treatment effect is "
        "larger when the binary moderator equals 1."
    )

    print(
        "- A significant subgroup treatment effect alone does NOT "
        "establish heterogeneity."
    )

    print(
        "- Targeted follow-up conclusions should use the Holm-adjusted "
        "interaction p-values, while remaining exploratory because the "
        "hypotheses were selected after descriptive subgroup review."
    )

    print(
        "- Channel tests are exploratory global interaction tests."
    )


if __name__ == "__main__":
    main()