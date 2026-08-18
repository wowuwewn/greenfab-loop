#!/usr/bin/env python3
"""생성한 dashboard_data.json을 커밋된 참조본과 허용오차로 비교한다."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    repository_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--actual", type=Path, required=True)
    parser.add_argument(
        "--reference",
        type=Path,
        default=repository_root / "data" / "outputs" / "detect" / "dashboard_data.json",
    )
    parser.add_argument("--absolute-tolerance", type=float, default=1e-12)
    parser.add_argument("--relative-tolerance", type=float, default=1e-12)
    return parser.parse_args()


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def compare_values(
    reference: Any,
    actual: Any,
    *,
    path: str = "$",
    absolute_tolerance: float,
    relative_tolerance: float,
) -> list[str]:
    differences: list[str] = []

    if isinstance(reference, dict) and isinstance(actual, dict):
        reference_keys = set(reference)
        actual_keys = set(actual)
        for missing in sorted(reference_keys - actual_keys):
            differences.append(f"{path}: actual에 키가 없음: {missing}")
        for extra in sorted(actual_keys - reference_keys):
            differences.append(f"{path}: actual에 참조본에 없는 키가 있음: {extra}")
        for key in sorted(reference_keys & actual_keys):
            differences.extend(
                compare_values(
                    reference[key],
                    actual[key],
                    path=f"{path}.{key}",
                    absolute_tolerance=absolute_tolerance,
                    relative_tolerance=relative_tolerance,
                )
            )
        return differences

    if isinstance(reference, list) and isinstance(actual, list):
        if len(reference) != len(actual):
            return [f"{path}: 길이 불일치 {len(reference)} != {len(actual)}"]
        for index, (reference_item, actual_item) in enumerate(zip(reference, actual)):
            differences.extend(
                compare_values(
                    reference_item,
                    actual_item,
                    path=f"{path}[{index}]",
                    absolute_tolerance=absolute_tolerance,
                    relative_tolerance=relative_tolerance,
                )
            )
        return differences

    numeric_types = (int, float)
    if (
        isinstance(reference, numeric_types)
        and not isinstance(reference, bool)
        and isinstance(actual, numeric_types)
        and not isinstance(actual, bool)
    ):
        if not math.isclose(
            float(reference),
            float(actual),
            abs_tol=absolute_tolerance,
            rel_tol=relative_tolerance,
        ):
            differences.append(f"{path}: 수치 불일치 {reference} != {actual}")
        return differences

    if reference != actual:
        differences.append(f"{path}: 값 불일치 {reference!r} != {actual!r}")
    return differences


def main() -> None:
    args = parse_args()
    differences = compare_values(
        load_json(args.reference),
        load_json(args.actual),
        absolute_tolerance=args.absolute_tolerance,
        relative_tolerance=args.relative_tolerance,
    )
    if differences:
        preview = "\n".join(f"- {item}" for item in differences[:20])
        raise SystemExit(
            f"참조 산출물과 {len(differences)}개 차이가 있습니다.\n{preview}"
        )
    print("참조 dashboard_data.json과 구조·값이 허용오차 안에서 일치합니다.")


if __name__ == "__main__":
    main()
