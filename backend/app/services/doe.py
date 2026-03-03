from __future__ import annotations

from itertools import product

import numpy as np

from ..models import Study, StudyDesignType


def _center_value(factor: dict) -> float:
    if factor.get('center') is not None:
        return float(factor['center'])
    return float((factor['low'] + factor['high']) / 2)


def _full_factorial(factors: list[dict], center_points: int) -> list[dict[str, float]]:
    levels = [[float(f['low']), float(f['high'])] for f in factors]
    names = [f['name'] for f in factors]
    runs = [{name: val for name, val in zip(names, values, strict=True)} for values in product(*levels)]

    center = {f['name']: _center_value(f) for f in factors}
    runs.extend([center.copy() for _ in range(center_points)])
    return runs


def _fractional_factorial(factors: list[dict], fraction_p: int, center_points: int) -> list[dict[str, float]]:
    # Simplified fractional implementation: subset of full factorial preserving balance.
    names = [f['name'] for f in factors]
    coded = list(product([-1, 1], repeat=len(factors)))

    if len(factors) >= 3 and fraction_p == 1:
        coded = [row for row in coded if row[-1] == int(np.prod(row[:-1]))]
    else:
        target = max(2 ** max(len(factors) - fraction_p, 1), 2)
        step = max(len(coded) // target, 1)
        coded = coded[::step][:target]

    runs: list[dict[str, float]] = []
    for row in coded:
        values = {}
        for idx, code in enumerate(row):
            f = factors[idx]
            values[names[idx]] = float(f['high'] if code > 0 else f['low'])
        runs.append(values)

    center = {f['name']: _center_value(f) for f in factors}
    runs.extend([center.copy() for _ in range(center_points)])
    return runs


def _mixture_2comp(factors: list[dict], center_points: int) -> list[dict[str, float]]:
    if len(factors) != 2:
        raise ValueError('Mixture 2-component design requires exactly 2 factors')

    f1, f2 = factors[0]['name'], factors[1]['name']
    points = [(1.0, 0.0), (0.0, 1.0), (0.75, 0.25), (0.5, 0.5), (0.25, 0.75)]
    runs = [{f1: p[0], f2: p[1]} for p in points]
    runs.extend([{f1: 0.5, f2: 0.5} for _ in range(center_points)])
    return runs


def generate_runs(study: Study, center_points: int = 3, fraction_p: int = 1) -> list[dict[str, float]]:
    if study.design_type == StudyDesignType.FULL_FACTORIAL:
        return _full_factorial(study.factors, center_points=center_points)
    if study.design_type == StudyDesignType.FRACTIONAL_FACTORIAL:
        return _fractional_factorial(study.factors, fraction_p=fraction_p, center_points=center_points)
    if study.design_type == StudyDesignType.MIXTURE_2COMP:
        return _mixture_2comp(study.factors, center_points=center_points)
    raise ValueError(f'Unsupported design type: {study.design_type}')
