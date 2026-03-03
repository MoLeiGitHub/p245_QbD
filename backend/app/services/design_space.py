from __future__ import annotations

import numpy as np

from ..models import Study


def _normalize_term(term: str) -> str:
    return term.replace("Q('", '').replace("')", '')


def _predict_row(coefficients: dict[str, float], values: dict[str, float]) -> float:
    total = 0.0
    for raw_term, coef in coefficients.items():
        term = _normalize_term(raw_term)
        if term == 'Intercept':
            total += coef
            continue
        if ':' in term:
            parts = term.split(':')
            prod = 1.0
            for part in parts:
                prod *= float(values.get(part, 0.0))
            total += coef * prod
        else:
            total += coef * float(values.get(term, 0.0))
    return float(total)


def generate_design_space(
    study: Study,
    analysis_summary: dict,
    *,
    x_factor: str,
    y_factor: str,
    fixed_factors: dict[str, float],
    grid_size: int = 30,
) -> dict:
    factor_map = {f['name']: f for f in study.factors}
    if x_factor not in factor_map or y_factor not in factor_map:
        raise ValueError('x_factor or y_factor not in study factors')

    x_values = np.linspace(float(factor_map[x_factor]['low']), float(factor_map[x_factor]['high']), grid_size)
    y_values = np.linspace(float(factor_map[y_factor]['low']), float(factor_map[y_factor]['high']), grid_size)

    defaults = {
        f['name']: float(f.get('center', (f['low'] + f['high']) / 2))
        for f in study.factors
    }
    defaults.update({k: float(v) for k, v in fixed_factors.items()})

    response_specs = {r['name']: r for r in study.responses}
    response_models = analysis_summary.get('responses', {})

    pass_matrix = np.zeros((grid_size, grid_size), dtype=int)
    predictions: list[dict] = []
    feasible_points: list[dict] = []

    for i, xv in enumerate(x_values):
        for j, yv in enumerate(y_values):
            row_values = defaults.copy()
            row_values[x_factor] = float(xv)
            row_values[y_factor] = float(yv)

            all_pass = True
            predicted_responses: dict[str, float] = {}
            for response_name, spec in response_specs.items():
                model = response_models.get(response_name)
                if not model or 'coefficients' not in model:
                    continue
                pred = _predict_row(model['coefficients'], row_values)
                predicted_responses[response_name] = pred

                lb = spec.get('lower_bound')
                ub = spec.get('upper_bound')
                if lb is not None and pred < float(lb):
                    all_pass = False
                if ub is not None and pred > float(ub):
                    all_pass = False

            pass_matrix[j, i] = 1 if all_pass else 0
            point = {
                x_factor: float(xv),
                y_factor: float(yv),
                'pass': bool(all_pass),
                'predictions': predicted_responses,
            }
            predictions.append(point)
            if all_pass:
                feasible_points.append(point)

    if feasible_points:
        x_pass = [p[x_factor] for p in feasible_points]
        y_pass = [p[y_factor] for p in feasible_points]
        bounds = {
            x_factor: {'min': float(min(x_pass)), 'max': float(max(x_pass))},
            y_factor: {'min': float(min(y_pass)), 'max': float(max(y_pass))},
        }
    else:
        bounds = {x_factor: None, y_factor: None}

    feasible_ratio = float(pass_matrix.sum() / pass_matrix.size)

    return {
        'x_factor': x_factor,
        'y_factor': y_factor,
        'grid_size': grid_size,
        'fixed_factors': defaults,
        'pass_matrix': pass_matrix.tolist(),
        'predictions': predictions,
        'feasible_bounds': bounds,
        'feasible_ratio': feasible_ratio,
    }
