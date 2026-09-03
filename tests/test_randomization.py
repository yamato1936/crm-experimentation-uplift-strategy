from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats


ROOT = Path(__file__).resolve().parents[1]

RAW_PATH = (
    ROOT
    / "data"
    / "raw"
    / "Hillstrom.csv"
)

SUMMARY_PATH = (
    ROOT
    / "data"
    / "processed"
    / "randomization_validation_summary.json"
)


NUMERIC_BINARY_COVARIATES = [
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


@pytest.fixture(scope="module")
def raw_data() -> pd.DataFrame:
    assert RAW_PATH.exists(), (
        f"Raw data not found: {RAW_PATH}"
    )

    return pd.read_csv(
        RAW_PATH
    )


@pytest.fixture(scope="module")
def summary() -> dict:
    assert SUMMARY_PATH.exists(), (
        "Randomization summary not found. "
        "Run `python src/validate_randomization.py` first."
    )

    with SUMMARY_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(
            file
        )


def standardized_mean_difference(
    a: pd.Series,
    b: pd.Series,
) -> float:
    """
    Pairwise standardized mean difference:

        (mean_a - mean_b)
        -----------------
        sqrt((var_a + var_b) / 2)

    Sample variances are used.
    """
    a_values = pd.to_numeric(
        a,
        errors="raise",
    ).to_numpy(
        dtype=float
    )

    b_values = pd.to_numeric(
        b,
        errors="raise",
    ).to_numpy(
        dtype=float
    )

    mean_difference = float(
        a_values.mean()
        - b_values.mean()
    )

    variance_a = float(
        a_values.var(
            ddof=1
        )
    )

    variance_b = float(
        b_values.var(
            ddof=1
        )
    )

    denominator = float(
        np.sqrt(
            (
                variance_a
                + variance_b
            )
            / 2.0
        )
    )

    if denominator <= 0.0:
        if np.isclose(
            mean_difference,
            0.0,
        ):
            return 0.0

        return float(
            np.inf
        )

    return (
        mean_difference
        / denominator
    )


def max_abs_smd_for_covariate(
    data: pd.DataFrame,
    treatment_column: str,
    groups: list[str],
    covariate: str,
    categorical: bool,
) -> float:
    values: list[
        float
    ] = []

    if categorical:
        levels = sorted(
            data[
                covariate
            ]
            .dropna()
            .unique()
            .tolist()
        )

        for (
            group_a,
            group_b,
        ) in combinations(
            groups,
            2,
        ):
            subset_a = data.loc[
                data[
                    treatment_column
                ].eq(
                    group_a
                ),
                covariate,
            ]

            subset_b = data.loc[
                data[
                    treatment_column
                ].eq(
                    group_b
                ),
                covariate,
            ]

            for level in levels:
                indicator_a = (
                    subset_a.eq(
                        level
                    )
                    .astype(
                        float
                    )
                )

                indicator_b = (
                    subset_b.eq(
                        level
                    )
                    .astype(
                        float
                    )
                )

                values.append(
                    abs(
                        standardized_mean_difference(
                            indicator_a,
                            indicator_b,
                        )
                    )
                )

    else:
        for (
            group_a,
            group_b,
        ) in combinations(
            groups,
            2,
        ):
            subset_a = data.loc[
                data[
                    treatment_column
                ].eq(
                    group_a
                ),
                covariate,
            ]

            subset_b = data.loc[
                data[
                    treatment_column
                ].eq(
                    group_b
                ),
                covariate,
            ]

            values.append(
                abs(
                    standardized_mean_difference(
                        subset_a,
                        subset_b,
                    )
                )
            )

    return float(
        max(
            values
        )
    )


def test_expected_raw_columns_exist(
    raw_data: pd.DataFrame,
) -> None:
    expected = {
        "segment",
        *NUMERIC_BINARY_COVARIATES,
        *CATEGORICAL_COVARIATES,
    }

    missing = (
        expected
        - set(
            raw_data.columns
        )
    )

    assert not missing, (
        f"Missing raw columns: {sorted(missing)}"
    )


def test_row_count_matches_validation_summary(
    raw_data: pd.DataFrame,
    summary: dict,
) -> None:
    assert len(
        raw_data
    ) == summary[
        "n_rows"
    ]


def test_treatment_groups_match_summary(
    raw_data: pd.DataFrame,
    summary: dict,
) -> None:
    observed_groups = set(
        raw_data[
            "segment"
        ].unique()
    )

    expected_groups = set(
        summary[
            "treatment_groups"
        ]
    )

    assert (
        observed_groups
        == expected_groups
    )


def test_treatment_counts_match_summary(
    raw_data: pd.DataFrame,
    summary: dict,
) -> None:
    observed_counts = (
        raw_data[
            "segment"
        ]
        .value_counts()
        .to_dict()
    )

    expected_counts = (
        summary[
            "srm"
        ][
            "observed_counts"
        ]
    )

    assert (
        observed_counts
        == expected_counts
    )


def test_srm_statistics_recompute_correctly(
    raw_data: pd.DataFrame,
    summary: dict,
) -> None:
    groups = summary[
        "treatment_groups"
    ]

    ratios = np.asarray(
        summary[
            "expected_ratios"
        ],
        dtype=float,
    )

    ratios = (
        ratios
        / ratios.sum()
    )

    observed = np.asarray(
        [
            (
                raw_data[
                    "segment"
                ]
                == group
            ).sum()
            for group in groups
        ],
        dtype=float,
    )

    expected = (
        observed.sum()
        * ratios
    )

    statistic = float(
        np.sum(
            (
                observed
                - expected
            ) ** 2
            / expected
        )
    )

    p_value = float(
        stats.chi2.sf(
            statistic,
            df=len(
                groups
            )
            - 1,
        )
    )

    reported = summary[
        "srm"
    ]

    assert statistic == pytest.approx(
        reported[
            "chi_square_statistic"
        ],
        abs=1e-12,
    )

    assert p_value == pytest.approx(
        reported[
            "p_value"
        ],
        abs=1e-12,
    )


def test_srm_flag_is_consistent_with_alpha(
    summary: dict,
) -> None:
    srm = summary[
        "srm"
    ]

    expected_flag = (
        srm[
            "p_value"
        ]
        < srm[
            "alpha"
        ]
    )

    assert (
        srm[
            "sample_ratio_mismatch_flag"
        ]
        == expected_flag
    )


def test_no_material_covariate_imbalance(
    raw_data: pd.DataFrame,
    summary: dict,
) -> None:
    groups = summary[
        "treatment_groups"
    ]

    threshold = float(
        summary[
            "smd_threshold"
        ]
    )

    covariate_maxima: dict[
        str,
        float,
    ] = {}

    for covariate in (
        NUMERIC_BINARY_COVARIATES
    ):
        covariate_maxima[
            covariate
        ] = (
            max_abs_smd_for_covariate(
                data=raw_data,
                treatment_column="segment",
                groups=groups,
                covariate=covariate,
                categorical=False,
            )
        )

    for covariate in (
        CATEGORICAL_COVARIATES
    ):
        covariate_maxima[
            covariate
        ] = (
            max_abs_smd_for_covariate(
                data=raw_data,
                treatment_column="segment",
                groups=groups,
                covariate=covariate,
                categorical=True,
            )
        )

    calculated_max = max(
        covariate_maxima.values()
    )

    # Allow a tiny tolerance for implementation differences
    # in floating-point variance calculation.
    assert calculated_max == pytest.approx(
        summary[
            "max_abs_smd"
        ],
        abs=1e-4,
    )

    independently_flagged = sorted(
        covariate
        for (
            covariate,
            max_abs_smd,
        ) in covariate_maxima.items()
        if max_abs_smd >= threshold
    )

    assert independently_flagged == sorted(
        summary[
            "imbalanced_covariates"
        ]
    )

    assert all(
        value < threshold
        for value in covariate_maxima.values()
    )


def test_randomization_interpretation_is_diagnostic(
    summary: dict,
) -> None:
    interpretation = (
        summary[
            "interpretation"
        ]
        .lower()
    )

    # Guard against accidentally changing the output to an
    # overclaim such as "randomization was proven successful".
    assert (
        "does not prove"
        in interpretation
    )