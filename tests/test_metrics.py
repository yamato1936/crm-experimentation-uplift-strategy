from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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

ATE_SUMMARY_PATH = (
    ROOT
    / "data"
    / "processed"
    / "ate_summary.json"
)


RAW_TO_ANALYSIS_TREATMENT = {
    "No E-Mail": "control",
    "Mens E-Mail": "mens_email",
    "Womens E-Mail": "womens_email",
}

EXPECTED_TREATMENTS = {
    "mens_email",
    "womens_email",
}

EXPECTED_OUTCOMES = {
    "visit",
    "conversion",
    "spend",
}

BINARY_OUTCOMES = {
    "visit",
    "conversion",
}


@pytest.fixture(scope="module")
def experiment_data() -> pd.DataFrame:
    assert RAW_PATH.exists(), (
        f"Raw data not found: {RAW_PATH}"
    )

    df = pd.read_csv(
        RAW_PATH
    )

    df[
        "treatment_group"
    ] = df[
        "segment"
    ].map(
        RAW_TO_ANALYSIS_TREATMENT
    )

    assert df[
        "treatment_group"
    ].notna().all()

    return df


@pytest.fixture(scope="module")
def ate_summary() -> dict[str, Any]:
    assert ATE_SUMMARY_PATH.exists(), (
        "ATE summary not found. "
        "Run `python src/estimate_ate.py` first."
    )

    with ATE_SUMMARY_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(
            file
        )


@pytest.fixture(scope="module")
def effects(
    ate_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    return ate_summary[
        "effects"
    ]


def welch_degrees_of_freedom(
    treatment: np.ndarray,
    control: np.ndarray,
) -> float:
    treatment = np.asarray(
        treatment,
        dtype=float,
    )

    control = np.asarray(
        control,
        dtype=float,
    )

    n_t = len(
        treatment
    )

    n_c = len(
        control
    )

    variance_t = float(
        treatment.var(
            ddof=1
        )
    )

    variance_c = float(
        control.var(
            ddof=1
        )
    )

    term_t = (
        variance_t
        / n_t
    )

    term_c = (
        variance_c
        / n_c
    )

    numerator = (
        term_t
        + term_c
    ) ** 2

    denominator = (
        term_t**2
        / (
            n_t
            - 1
        )
        + term_c**2
        / (
            n_c
            - 1
        )
    )

    if denominator <= 0.0:
        return float(
            np.inf
        )

    return float(
        numerator
        / denominator
    )


def holm_adjust(
    p_values: np.ndarray,
) -> np.ndarray:
    """
    Holm step-down adjusted p-values.
    """
    p_values = np.asarray(
        p_values,
        dtype=float,
    )

    m = len(
        p_values
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
        sorted_p
    ):
        multiplier = (
            m
            - rank
        )

        adjusted = min(
            1.0,
            multiplier
            * p_value,
        )

        running_max = max(
            running_max,
            adjusted,
        )

        adjusted_sorted[
            rank
        ] = running_max

    adjusted = np.empty(
        m,
        dtype=float,
    )

    adjusted[
        order
    ] = adjusted_sorted

    return adjusted


def raw_values(
    data: pd.DataFrame,
    treatment: str,
    outcome: str,
) -> np.ndarray:
    return (
        data.loc[
            data[
                "treatment_group"
            ].eq(
                treatment
            ),
            outcome,
        ]
        .to_numpy(
            dtype=float
        )
    )


def test_exactly_six_primary_ate_tests(
    effects: list[dict[str, Any]],
) -> None:
    assert len(
        effects
    ) == 6

    observed = {
        (
            effect[
                "treatment"
            ],
            effect[
                "outcome"
            ],
        )
        for effect in effects
    }

    expected = {
        (
            treatment,
            outcome,
        )
        for treatment
        in EXPECTED_TREATMENTS
        for outcome
        in EXPECTED_OUTCOMES
    }

    assert observed == expected


@pytest.mark.parametrize(
    "outcome",
    [
        "visit",
        "conversion",
    ],
)
def test_binary_outcomes_are_binary(
    experiment_data: pd.DataFrame,
    outcome: str,
) -> None:
    observed = set(
        experiment_data[
            outcome
        ].dropna()
    )

    assert observed.issubset(
        {
            0,
            1,
        }
    )


def test_spend_is_nonnegative(
    experiment_data: pd.DataFrame,
) -> None:
    assert (
        experiment_data[
            "spend"
        ]
        >= 0
    ).all()


def test_reported_arm_means_and_ate_match_raw_data(
    experiment_data: pd.DataFrame,
    effects: list[dict[str, Any]],
) -> None:
    for effect in effects:
        treatment = effect[
            "treatment"
        ]

        control = effect[
            "control"
        ]

        outcome = effect[
            "outcome"
        ]

        treatment_values = raw_values(
            experiment_data,
            treatment,
            outcome,
        )

        control_values = raw_values(
            experiment_data,
            control,
            outcome,
        )

        treatment_mean = float(
            treatment_values.mean()
        )

        control_mean = float(
            control_values.mean()
        )

        ate = (
            treatment_mean
            - control_mean
        )

        assert len(
            treatment_values
        ) == effect[
            "treatment_n"
        ]

        assert len(
            control_values
        ) == effect[
            "control_n"
        ]

        assert treatment_mean == pytest.approx(
            effect[
                "treatment_mean"
            ],
            abs=1e-12,
        )

        assert control_mean == pytest.approx(
            effect[
                "control_mean"
            ],
            abs=1e-12,
        )

        assert ate == pytest.approx(
            effect[
                "ate"
            ],
            abs=1e-12,
        )


def test_relative_lift_definition(
    effects: list[dict[str, Any]],
) -> None:
    for effect in effects:
        expected = (
            effect[
                "ate"
            ]
            / effect[
                "control_mean"
            ]
        )

        assert expected == pytest.approx(
            effect[
                "relative_lift"
            ],
            abs=1e-12,
        )


def test_binary_standard_errors_and_p_values(
    experiment_data: pd.DataFrame,
    effects: list[dict[str, Any]],
    ate_summary: dict[str, Any],
) -> None:
    alpha = float(
        ate_summary[
            "alpha"
        ]
    )

    critical = float(
        stats.norm.ppf(
            1.0
            - alpha
            / 2.0
        )
    )

    for effect in effects:
        outcome = effect[
            "outcome"
        ]

        if outcome not in BINARY_OUTCOMES:
            continue

        treatment_values = raw_values(
            experiment_data,
            effect[
                "treatment"
            ],
            outcome,
        )

        control_values = raw_values(
            experiment_data,
            effect[
                "control"
            ],
            outcome,
        )

        n_t = len(
            treatment_values
        )

        n_c = len(
            control_values
        )

        p_t = float(
            treatment_values.mean()
        )

        p_c = float(
            control_values.mean()
        )

        ate = (
            p_t
            - p_c
        )

        # Unpooled SE for confidence interval.
        standard_error = float(
            np.sqrt(
                p_t
                * (
                    1.0
                    - p_t
                )
                / n_t
                + p_c
                * (
                    1.0
                    - p_c
                )
                / n_c
            )
        )

        ci_low = (
            ate
            - critical
            * standard_error
        )

        ci_high = (
            ate
            + critical
            * standard_error
        )

        assert standard_error == pytest.approx(
            effect[
                "standard_error"
            ],
            abs=1e-12,
        )

        assert ci_low == pytest.approx(
            effect[
                "ci_low"
            ],
            abs=1e-12,
        )

        assert ci_high == pytest.approx(
            effect[
                "ci_high"
            ],
            abs=1e-12,
        )

        # Pooled SE under H0 for the two-proportion z-test.
        pooled_probability = float(
            (
                treatment_values.sum()
                + control_values.sum()
            )
            / (
                n_t
                + n_c
            )
        )

        null_standard_error = float(
            np.sqrt(
                pooled_probability
                * (
                    1.0
                    - pooled_probability
                )
                * (
                    1.0
                    / n_t
                    + 1.0
                    / n_c
                )
            )
        )

        z_statistic = (
            ate
            / null_standard_error
        )

        p_value = float(
            2.0
            * stats.norm.sf(
                abs(
                    z_statistic
                )
            )
        )

        assert z_statistic == pytest.approx(
            effect[
                "test_statistic"
            ],
            rel=1e-10,
        )

        assert p_value == pytest.approx(
            effect[
                "p_value"
            ],
            rel=1e-8,
            abs=1e-300,
        )


def test_spend_uses_all_randomized_users_including_zeros(
    experiment_data: pd.DataFrame,
    effects: list[dict[str, Any]],
) -> None:
    for effect in effects:
        if effect[
            "outcome"
        ] != "spend":
            continue

        treatment_values = raw_values(
            experiment_data,
            effect[
                "treatment"
            ],
            "spend",
        )

        all_user_mean = float(
            treatment_values.mean()
        )

        positive_only = (
            treatment_values[
                treatment_values > 0
            ]
        )

        assert len(
            positive_only
        ) < len(
            treatment_values
        )

        positive_only_mean = float(
            positive_only.mean()
        )

        assert all_user_mean == pytest.approx(
            effect[
                "treatment_mean"
            ],
            abs=1e-12,
        )

        # Guard against accidentally changing the estimand to
        # spend conditional on conversion / positive spend.
        assert not np.isclose(
            all_user_mean,
            positive_only_mean,
        )


def test_spend_welch_inference(
    experiment_data: pd.DataFrame,
    effects: list[dict[str, Any]],
    ate_summary: dict[str, Any],
) -> None:
    alpha = float(
        ate_summary[
            "alpha"
        ]
    )

    for effect in effects:
        if effect[
            "outcome"
        ] != "spend":
            continue

        treatment_values = raw_values(
            experiment_data,
            effect[
                "treatment"
            ],
            "spend",
        )

        control_values = raw_values(
            experiment_data,
            effect[
                "control"
            ],
            "spend",
        )

        n_t = len(
            treatment_values
        )

        n_c = len(
            control_values
        )

        variance_t = float(
            treatment_values.var(
                ddof=1
            )
        )

        variance_c = float(
            control_values.var(
                ddof=1
            )
        )

        ate = float(
            treatment_values.mean()
            - control_values.mean()
        )

        standard_error = float(
            np.sqrt(
                variance_t
                / n_t
                + variance_c
                / n_c
            )
        )

        df = (
            welch_degrees_of_freedom(
                treatment_values,
                control_values,
            )
        )

        assert np.isfinite(
            df
        )

        statistic = (
            ate
            / standard_error
        )

        p_value = float(
            2.0
            * stats.t.sf(
                abs(
                    statistic
                ),
                df=df,
            )
        )

        critical = float(
            stats.t.ppf(
                1.0
                - alpha
                / 2.0,
                df=df,
            )
        )

        ci_low = (
            ate
            - critical
            * standard_error
        )

        ci_high = (
            ate
            + critical
            * standard_error
        )

        assert standard_error == pytest.approx(
            effect[
                "standard_error"
            ],
            rel=1e-10,
        )

        # This specifically protects the Welch-df bug that
        # previously returned Infinity for a valid denominator.
        reported_df = float(
            effect[
                "degrees_of_freedom"
            ]
        )

        assert np.isfinite(
            reported_df
        )

        assert reported_df == pytest.approx(
            df,
            rel=1e-8,
        )

        assert statistic == pytest.approx(
            effect[
                "test_statistic"
            ],
            rel=1e-8,
        )

        assert p_value == pytest.approx(
            effect[
                "p_value"
            ],
            rel=1e-5,
        )

        # scipy t-critical vs implementation details can produce
        # tiny numerical differences at df ~ tens of thousands.
        assert ci_low == pytest.approx(
            effect[
                "ci_low"
            ],
            abs=1e-4,
        )

        assert ci_high == pytest.approx(
            effect[
                "ci_high"
            ],
            abs=1e-4,
        )


def test_confidence_intervals_contain_point_estimate(
    effects: list[dict[str, Any]],
) -> None:
    for effect in effects:
        assert (
            effect[
                "ci_low"
            ]
            <= effect[
                "ate"
            ]
            <= effect[
                "ci_high"
            ]
        )

        if effect[
            "outcome"
        ] == "spend":
            assert (
                effect[
                    "bootstrap_ci_low"
                ]
                <= effect[
                    "ate"
                ]
                <= effect[
                    "bootstrap_ci_high"
                ]
            )


def test_holm_adjustment_is_correct(
    effects: list[dict[str, Any]],
) -> None:
    raw_p_values = np.asarray(
        [
            effect[
                "p_value"
            ]
            for effect in effects
        ],
        dtype=float,
    )

    expected_adjusted = (
        holm_adjust(
            raw_p_values
        )
    )

    reported_adjusted = np.asarray(
        [
            effect[
                "p_value_holm"
            ]
            for effect in effects
        ],
        dtype=float,
    )

    assert reported_adjusted == pytest.approx(
        expected_adjusted,
        rel=1e-10,
        abs=1e-300,
    )

    assert np.all(
        reported_adjusted
        >= raw_p_values
    )

    assert np.all(
        reported_adjusted
        <= 1.0
    )


def test_significance_flags_match_p_values(
    effects: list[dict[str, Any]],
    ate_summary: dict[str, Any],
) -> None:
    alpha = float(
        ate_summary[
            "alpha"
        ]
    )

    for effect in effects:
        assert effect[
            "significant_raw"
        ] == (
            effect[
                "p_value"
            ]
            < alpha
        )

        assert effect[
            "significant_holm"
        ] == (
            effect[
                "p_value_holm"
            ]
            < alpha
        )