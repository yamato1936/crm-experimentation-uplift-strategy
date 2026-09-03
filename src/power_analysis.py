from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats


DEFAULT_MDES = [
    0.10,
    0.20,
    0.30,
    0.40,
    0.50,
]

DEFAULT_NI_MARGINS = [
    0.10,
    0.20,
    0.30,
    0.40,
    0.50,
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Plan a prospective RCT comparing a frozen uplift-targeting "
            "policy with Send All in the Hillstrom experiment."
        )
    )

    parser.add_argument(
        "--predictions",
        default="data/processed/uplift_predictions.csv",
        help="Held-out predictions from uplift_model.py.",
    )

    parser.add_argument(
        "--policy-results",
        default="data/processed/policy_evaluation.csv",
        help="Held-out policy evaluation results.",
    )

    parser.add_argument(
        "--treatment",
        default="womens_email",
        help="Email treatment being evaluated.",
    )

    parser.add_argument(
        "--outcome",
        default="spend",
        help="Primary RCT outcome.",
    )

    parser.add_argument(
        "--policy",
        default="top_10_pct",
        help="Frozen targeting policy to compare with Send All.",
    )

    parser.add_argument(
        "--target-rate",
        type=float,
        default=0.10,
        help="Expected treatment rate under the targeting policy.",
    )

    parser.add_argument(
        "--alpha",
        type=float,
        default=0.05,
        help="Type-I error rate.",
    )

    parser.add_argument(
        "--power",
        type=float,
        default=0.80,
        help="Target statistical power.",
    )

    parser.add_argument(
        "--mdes",
        nargs="+",
        type=float,
        default=DEFAULT_MDES,
        help=(
            "Absolute spend-per-user differences for two-sided "
            "difference-detection sensitivity."
        ),
    )

    parser.add_argument(
        "--ni-margins",
        nargs="+",
        type=float,
        default=DEFAULT_NI_MARGINS,
        help=(
            "Non-inferiority margins. Positive M means Top-k may lose "
            "at most M spend/user relative to Send All."
        ),
    )

    parser.add_argument(
        "--ni-assumed-true-difference",
        type=float,
        default=0.0,
        help=(
            "Assumed true Top-k minus Send-All difference for "
            "non-inferiority power calculations. Default 0 is conservative "
            "relative to claiming a targeting benefit and avoids treating "
            "the observed holdout estimate as truth."
        ),
    )

    parser.add_argument(
        "--planning-sd",
        type=float,
        default=None,
        help=(
            "Optional planning SD override. If omitted, uses the larger "
            "held-out SD from treatment and control."
        ),
    )

    parser.add_argument(
        "--attrition-rate",
        type=float,
        default=0.0,
        help="Expected fraction of randomized units lost before analysis.",
    )

    parser.add_argument(
        "--output-dir",
        default="data/processed",
        help="Output directory.",
    )

    return parser.parse_args()


def validate_args(
    args: argparse.Namespace,
) -> None:
    if not 0 < args.alpha < 1:
        raise ValueError(
            "--alpha must be between 0 and 1."
        )

    if not 0 < args.power < 1:
        raise ValueError(
            "--power must be between 0 and 1."
        )

    if not 0 < args.target_rate < 1:
        raise ValueError(
            "--target-rate must be between 0 and 1."
        )

    if not 0 <= args.attrition_rate < 1:
        raise ValueError(
            "--attrition-rate must be in [0, 1)."
        )

    if any(
        value <= 0
        for value in args.mdes
    ):
        raise ValueError(
            "All MDEs must be positive."
        )

    if any(
        value <= 0
        for value in args.ni_margins
    ):
        raise ValueError(
            "All non-inferiority margins must be positive."
        )

    if (
        args.planning_sd is not None
        and args.planning_sd <= 0
    ):
        raise ValueError(
            "--planning-sd must be positive."
        )


def load_predictions(
    path: Path,
    treatment: str,
    outcome: str,
) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Predictions file not found: {path}"
        )

    df = pd.read_csv(
        path
    )

    required = {
        "treatment",
        "outcome",
        "treatment_indicator",
        "observed_outcome",
    }

    missing = (
        required
        - set(
            df.columns
        )
    )

    if missing:
        raise ValueError(
            f"Missing prediction columns: {sorted(missing)}"
        )

    data = (
        df.loc[
            df["treatment"].eq(
                treatment
            )
            & df["outcome"].eq(
                outcome
            )
        ]
        .copy()
        .reset_index(
            drop=True
        )
    )

    if data.empty:
        raise ValueError(
            f"No predictions found for {treatment} / {outcome}."
        )

    data[
        "treatment_indicator"
    ] = pd.to_numeric(
        data[
            "treatment_indicator"
        ],
        errors="raise",
    )

    data[
        "observed_outcome"
    ] = pd.to_numeric(
        data[
            "observed_outcome"
        ],
        errors="raise",
    )

    return data


def load_policy_result(
    path: Path,
    treatment: str,
    outcome: str,
    policy: str,
) -> dict[str, float]:
    if not path.exists():
        raise FileNotFoundError(
            f"Policy results file not found: {path}"
        )

    df = pd.read_csv(
        path
    )

    required = {
        "treatment",
        "outcome",
        "policy",
        "policy_value",
        "incremental_vs_send_all",
        "incremental_vs_send_all_ci_low",
        "incremental_vs_send_all_ci_high",
    }

    missing = (
        required
        - set(
            df.columns
        )
    )

    if missing:
        raise ValueError(
            f"Missing policy-result columns: {sorted(missing)}"
        )

    row = df.loc[
        df["treatment"].eq(
            treatment
        )
        & df["outcome"].eq(
            outcome
        )
        & df["policy"].eq(
            policy
        )
    ]

    if len(
        row
    ) != 1:
        raise ValueError(
            "Expected exactly one policy result for "
            f"{treatment} / {outcome} / {policy}, found {len(row)}."
        )

    record = row.iloc[
        0
    ]

    return {
        "policy_value": float(
            record[
                "policy_value"
            ]
        ),
        "observed_difference_vs_send_all": float(
            record[
                "incremental_vs_send_all"
            ]
        ),
        "observed_difference_ci_low": float(
            record[
                "incremental_vs_send_all_ci_low"
            ]
        ),
        "observed_difference_ci_high": float(
            record[
                "incremental_vs_send_all_ci_high"
            ]
        ),
    }


def estimate_planning_variance(
    data: pd.DataFrame,
    planning_sd_override: float | None,
) -> dict[str, float | str]:
    treated = (
        data.loc[
            data[
                "treatment_indicator"
            ].eq(
                1
            ),
            "observed_outcome",
        ]
        .to_numpy(
            dtype=float
        )
    )

    control = (
        data.loc[
            data[
                "treatment_indicator"
            ].eq(
                0
            ),
            "observed_outcome",
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
        raise ValueError(
            "At least two observations per randomized arm are required."
        )

    treated_sd = float(
        treated.std(
            ddof=1
        )
    )

    control_sd = float(
        control.std(
            ddof=1
        )
    )

    if planning_sd_override is None:
        # Conservative planning choice:
        # use the larger observed arm SD.
        planning_sd = max(
            treated_sd,
            control_sd,
        )

        source = (
            "max held-out treatment/control SD"
        )
    else:
        planning_sd = float(
            planning_sd_override
        )

        source = (
            "user-specified planning SD"
        )

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
        "treated_mean": float(
            treated.mean()
        ),
        "control_mean": float(
            control.mean()
        ),
        "treated_sd": treated_sd,
        "control_sd": control_sd,
        "planning_sd": planning_sd,
        "planning_sd_source": source,
    }


def inflate_for_attrition(
    n: int,
    attrition_rate: float,
) -> int:
    return int(
        np.ceil(
            n
            / (
                1.0
                - attrition_rate
            )
        )
    )


def two_sided_difference_sample_size(
    effect: float,
    sd: float,
    alpha: float,
    power: float,
) -> int:
    """
    Equal-sized two-arm normal approximation:

        n_per_arm
          = 2 sigma^2
            (z_(1-alpha/2) + z_power)^2
            / delta^2

    This is a planning approximation for a difference in mean
    spend per randomized user.
    """
    z_alpha = float(
        stats.norm.ppf(
            1.0
            - alpha / 2.0
        )
    )

    z_power = float(
        stats.norm.ppf(
            power
        )
    )

    n = (
        2.0
        * sd**2
        * (
            z_alpha
            + z_power
        )**2
        / effect**2
    )

    return int(
        np.ceil(
            n
        )
    )


def noninferiority_sample_size(
    margin: float,
    assumed_true_difference: float,
    sd: float,
    alpha: float,
    power: float,
) -> int | None:
    """
    Non-inferiority estimand:

        Delta = V(Targeting) - V(Send All)

    Hypotheses:

        H0: Delta <= -M
        H1: Delta >  -M

    where M > 0 is the maximum acceptable loss in spend/user.

    Under assumed true difference Delta_true, the distance from the
    null boundary is:

        Delta_true + M

    The distance must be positive for non-inferiority to be attainable.
    """
    effective_difference = (
        assumed_true_difference
        + margin
    )

    if effective_difference <= 0:
        return None

    z_alpha = float(
        stats.norm.ppf(
            1.0
            - alpha
        )
    )

    z_power = float(
        stats.norm.ppf(
            power
        )
    )

    n = (
        2.0
        * sd**2
        * (
            z_alpha
            + z_power
        )**2
        / effective_difference**2
    )

    return int(
        np.ceil(
            n
        )
    )


def build_mde_table(
    mdes: list[float],
    planning_sd: float,
    alpha: float,
    power: float,
    attrition_rate: float,
    target_rate: float,
) -> pd.DataFrame:
    records: list[
        dict[str, Any]
    ] = []

    for mde in mdes:
        n_per_arm = (
            two_sided_difference_sample_size(
                effect=mde,
                sd=planning_sd,
                alpha=alpha,
                power=power,
            )
        )

        randomized_per_arm = (
            inflate_for_attrition(
                n=n_per_arm,
                attrition_rate=attrition_rate,
            )
        )

        total_randomized = (
            2
            * randomized_per_arm
        )

        # Future RCT:
        #
        # Arm A: Send All
        # Arm B: Frozen Top-k targeting.
        send_all_emails = (
            randomized_per_arm
        )

        targeting_emails = int(
            np.ceil(
                randomized_per_arm
                * target_rate
            )
        )

        records.append(
            {
                "analysis": (
                    "two_sided_difference_detection"
                ),
                "mde_spend_per_user": float(
                    mde
                ),
                "standardized_effect_size": float(
                    mde
                    / planning_sd
                ),
                "alpha": alpha,
                "power": power,
                "required_analyzable_n_per_arm": (
                    n_per_arm
                ),
                "attrition_rate": (
                    attrition_rate
                ),
                "required_randomized_n_per_arm": (
                    randomized_per_arm
                ),
                "required_total_randomized_n": (
                    total_randomized
                ),
                "expected_send_all_emails": (
                    send_all_emails
                ),
                "expected_targeting_emails": (
                    targeting_emails
                ),
            }
        )

    return pd.DataFrame(
        records
    )


def build_noninferiority_table(
    margins: list[float],
    assumed_true_difference: float,
    planning_sd: float,
    alpha: float,
    power: float,
    attrition_rate: float,
    target_rate: float,
) -> pd.DataFrame:
    records: list[
        dict[str, Any]
    ] = []

    for margin in margins:
        n_per_arm = (
            noninferiority_sample_size(
                margin=margin,
                assumed_true_difference=(
                    assumed_true_difference
                ),
                sd=planning_sd,
                alpha=alpha,
                power=power,
            )
        )

        effective_difference = (
            assumed_true_difference
            + margin
        )

        if n_per_arm is None:
            randomized_per_arm = None
            total_randomized = None
            send_all_emails = None
            targeting_emails = None
        else:
            randomized_per_arm = (
                inflate_for_attrition(
                    n=n_per_arm,
                    attrition_rate=(
                        attrition_rate
                    ),
                )
            )

            total_randomized = (
                2
                * randomized_per_arm
            )

            send_all_emails = (
                randomized_per_arm
            )

            targeting_emails = int(
                np.ceil(
                    randomized_per_arm
                    * target_rate
                )
            )

        records.append(
            {
                "analysis": (
                    "noninferiority"
                ),
                "ni_margin_spend_per_user": float(
                    margin
                ),
                "null_boundary": float(
                    -margin
                ),
                "assumed_true_difference": float(
                    assumed_true_difference
                ),
                "distance_from_null_boundary": float(
                    effective_difference
                ),
                "standardized_distance": (
                    float(
                        effective_difference
                        / planning_sd
                    )
                    if effective_difference > 0
                    else None
                ),
                "alpha_one_sided": alpha,
                "power": power,
                "required_analyzable_n_per_arm": (
                    n_per_arm
                ),
                "attrition_rate": (
                    attrition_rate
                ),
                "required_randomized_n_per_arm": (
                    randomized_per_arm
                ),
                "required_total_randomized_n": (
                    total_randomized
                ),
                "expected_send_all_emails": (
                    send_all_emails
                ),
                "expected_targeting_emails": (
                    targeting_emails
                ),
                "design_feasible_under_assumption": bool(
                    effective_difference > 0
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
            for key, item in value.items()
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
    ) and not np.isfinite(
        value
    ):
        return None

    return value


def build_summary(
    args: argparse.Namespace,
    variance_info: dict[str, Any],
    policy_info: dict[str, float],
    mde_table: pd.DataFrame,
    ni_table: pd.DataFrame,
) -> dict[str, Any]:
    return clean_json_value(
        {
            "prospective_experiment": {
                "arm_a": (
                    "Send All: send Women's Email to every "
                    "eligible randomized user."
                ),
                "arm_b": (
                    "Frozen Targeting Policy: apply the frozen uplift "
                    f"policy and send to approximately "
                    f"{100 * args.target_rate:.0f}% of eligible users."
                ),
                "randomization_unit": "eligible user",
                "primary_outcome": args.outcome,
                "estimand": (
                    "mean spend per randomized user under targeting "
                    "minus mean spend per randomized user under Send All"
                ),
            },
            "historical_context": {
                "treatment": (
                    args.treatment
                ),
                "policy": (
                    args.policy
                ),
                **policy_info,
            },
            "variance_planning": (
                variance_info
            ),
            "statistical_design": {
                "alpha": args.alpha,
                "power": args.power,
                "attrition_rate": (
                    args.attrition_rate
                ),
                "two_sided_mde_analysis": (
                    "Sensitivity analysis for detecting an absolute "
                    "difference in mean spend/user."
                ),
                "noninferiority_hypotheses": (
                    "H0: Targeting - SendAll <= -margin; "
                    "H1: Targeting - SendAll > -margin."
                ),
                "noninferiority_assumed_true_difference": (
                    args.ni_assumed_true_difference
                ),
            },
            "mde_sensitivity": (
                mde_table.to_dict(
                    orient="records"
                )
            ),
            "noninferiority_sensitivity": (
                ni_table.to_dict(
                    orient="records"
                )
            ),
            "interpretation_guardrails": [
                (
                    "The observed holdout Top-k versus Send-All difference "
                    "is reported as context but is not automatically treated "
                    "as the true effect for prospective power planning."
                ),
                (
                    "The planning SD uses the larger observed held-out arm SD "
                    "unless explicitly overridden."
                ),
                (
                    "Spend is revenue-like, not profit. A business decision "
                    "still requires margin and delivery-cost information."
                ),
                (
                    "The Top-k scoring rule, model parameters, features and "
                    "targeting threshold must be frozen before the prospective "
                    "RCT begins."
                ),
                (
                    "Sample-size calculations use large-sample normal "
                    "approximations. Spend is highly zero-inflated, so the "
                    "final experiment analysis should retain robust or "
                    "bootstrap uncertainty checks."
                ),
            ],
        }
    )


def save_outputs(
    output_dir: Path,
    mde_table: pd.DataFrame,
    ni_table: pd.DataFrame,
    summary: dict[str, Any],
) -> None:
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    mde_table.to_csv(
        output_dir
        / "power_mde_sensitivity.csv",
        index=False,
    )

    ni_table.to_csv(
        output_dir
        / "power_noninferiority_sensitivity.csv",
        index=False,
    )

    with (
        output_dir
        / "power_summary.json"
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
    variance_info: dict[str, Any],
    policy_info: dict[str, float],
    mde_table: pd.DataFrame,
    ni_table: pd.DataFrame,
    args: argparse.Namespace,
) -> None:
    print(
        "\n=== Historical Planning Inputs ==="
    )

    print(
        f"Treatment: {args.treatment}"
    )

    print(
        f"Frozen policy candidate: {args.policy}"
    )

    print(
        f"Held-out treated SD: "
        f"{variance_info['treated_sd']:.6f}"
    )

    print(
        f"Held-out control SD: "
        f"{variance_info['control_sd']:.6f}"
    )

    print(
        f"Planning SD: "
        f"{variance_info['planning_sd']:.6f}"
    )

    print(
        f"Planning SD source: "
        f"{variance_info['planning_sd_source']}"
    )

    print(
        f"Observed Top-k minus Send-All difference: "
        f"{policy_info['observed_difference_vs_send_all']:.6f}"
    )

    print(
        "Observed 95% CI: "
        f"[{policy_info['observed_difference_ci_low']:.6f}, "
        f"{policy_info['observed_difference_ci_high']:.6f}]"
    )

    print(
        "\n=== Two-sided Spend MDE Sensitivity ==="
    )

    mde_display = mde_table[
        [
            "mde_spend_per_user",
            "standardized_effect_size",
            "required_analyzable_n_per_arm",
            "required_randomized_n_per_arm",
            "required_total_randomized_n",
        ]
    ].copy()

    print(
        mde_display.to_string(
            index=False,
            float_format=lambda value: (
                f"{value:.4f}"
            ),
        )
    )

    print(
        "\n=== Non-inferiority Sensitivity ==="
    )

    print(
        "H0: Targeting - Send All <= -margin"
    )

    print(
        "H1: Targeting - Send All > -margin"
    )

    print(
        f"Assumed true difference for planning: "
        f"{args.ni_assumed_true_difference:.4f}"
    )

    ni_display = ni_table[
        [
            "ni_margin_spend_per_user",
            "null_boundary",
            "distance_from_null_boundary",
            "required_analyzable_n_per_arm",
            "required_randomized_n_per_arm",
            "required_total_randomized_n",
        ]
    ].copy()

    print(
        ni_display.to_string(
            index=False,
            float_format=lambda value: (
                f"{value:.4f}"
            ),
        )
    )

    print(
        "\nInterpretation:"
    )

    print(
        "- The non-inferiority margin is a business tolerance, "
        "not a number that should be selected only because it "
        "produces a convenient sample size."
    )

    print(
        "- The observed holdout difference is descriptive context; "
        "the default prospective design assumes a true difference of 0."
    )

    print(
        "- The uplift model and Top-k policy must be frozen before "
        "new experiment outcomes are observed."
    )

    print(
        "- Profit optimization still requires gross margin and "
        "delivery-cost inputs that are absent from the Hillstrom data."
    )


def main() -> None:
    args = parse_args()

    validate_args(
        args
    )

    predictions_path = Path(
        args.predictions
    )

    policy_results_path = Path(
        args.policy_results
    )

    data = load_predictions(
        path=predictions_path,
        treatment=args.treatment,
        outcome=args.outcome,
    )

    variance_info = (
        estimate_planning_variance(
            data=data,
            planning_sd_override=(
                args.planning_sd
            ),
        )
    )

    policy_info = load_policy_result(
        path=policy_results_path,
        treatment=args.treatment,
        outcome=args.outcome,
        policy=args.policy,
    )

    planning_sd = float(
        variance_info[
            "planning_sd"
        ]
    )

    mde_table = build_mde_table(
        mdes=args.mdes,
        planning_sd=planning_sd,
        alpha=args.alpha,
        power=args.power,
        attrition_rate=args.attrition_rate,
        target_rate=args.target_rate,
    )

    ni_table = (
        build_noninferiority_table(
            margins=args.ni_margins,
            assumed_true_difference=(
                args.ni_assumed_true_difference
            ),
            planning_sd=planning_sd,
            alpha=args.alpha,
            power=args.power,
            attrition_rate=args.attrition_rate,
            target_rate=args.target_rate,
        )
    )

    summary = build_summary(
        args=args,
        variance_info=variance_info,
        policy_info=policy_info,
        mde_table=mde_table,
        ni_table=ni_table,
    )

    save_outputs(
        output_dir=Path(
            args.output_dir
        ),
        mde_table=mde_table,
        ni_table=ni_table,
        summary=summary,
    )

    print_report(
        variance_info=variance_info,
        policy_info=policy_info,
        mde_table=mde_table,
        ni_table=ni_table,
        args=args,
    )


if __name__ == "__main__":
    main()