from __future__ import annotations

import math
from itertools import combinations

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.formula.api import ols
from statsmodels.stats.anova import anova_lm

from ..models import Study


P_VALUE_SIG = 0.05


def build_analysis_df(study: Study) -> pd.DataFrame:
    rows: list[dict] = []
    for run in study.runs:
        if not run.result:
            continue
        row = {'run_id': run.id}
        row.update(run.factor_values)
        row.update(run.result.response_values)
        rows.append(row)

    if not rows:
        raise ValueError('No results available. Import results before analysis.')
    return pd.DataFrame(rows)


def _formula(response_name: str, factor_names: list[str]) -> str:
    terms = factor_names.copy()
    terms.extend([f'{a}:{b}' for a, b in combinations(factor_names, 2)])
    return f"Q('{response_name}') ~ " + ' + '.join([f"Q('{t}')" for t in terms])


def _curvature_p(df: pd.DataFrame, response_name: str, factors: list[dict]) -> float | None:
    factor_names = [f['name'] for f in factors]
    centers = {f['name']: f.get('center', (f['low'] + f['high']) / 2) for f in factors}

    center_mask = np.ones(len(df), dtype=bool)
    for fn in factor_names:
        center_mask &= np.isclose(df[fn].astype(float), float(centers[fn]), rtol=1e-5, atol=1e-8)

    if center_mask.sum() < 1 or (~center_mask).sum() < 2:
        return None

    local = df.copy()
    local['center_indicator'] = center_mask.astype(int)
    terms = [f"Q('{f}')" for f in factor_names] + ['center_indicator']
    model = ols(f"Q('{response_name}') ~ {' + '.join(terms)}", data=local).fit()
    if 'center_indicator' not in model.pvalues:
        return None
    return float(model.pvalues['center_indicator'])


def _lack_of_fit_p(df: pd.DataFrame, response_name: str, factor_names: list[str], residual_ss: float, residual_df: int) -> float | None:
    grouped = df.groupby(factor_names, dropna=False)[response_name].agg(['count', 'var'])
    if grouped.empty:
        return None

    pure_error_df = int((grouped['count'] - 1).clip(lower=0).sum())
    if pure_error_df <= 0:
        return None

    var_component = grouped['var'].fillna(0.0)
    pure_error_ss = float(((grouped['count'] - 1).clip(lower=0) * var_component).sum())

    lof_df = int(residual_df - pure_error_df)
    lof_ss = float(residual_ss - pure_error_ss)
    if lof_df <= 0 or pure_error_ss <= 0 or lof_ss < 0:
        return None

    f_value = (lof_ss / lof_df) / (pure_error_ss / pure_error_df)
    return float(1 - stats.f.cdf(f_value, lof_df, pure_error_df))


def _half_normal(model) -> list[dict]:
    tvals = model.tvalues.drop(labels=['Intercept'], errors='ignore')
    if tvals.empty:
        return []

    effects = np.abs(tvals.to_numpy(dtype=float))
    order = np.argsort(effects)
    sorted_effects = effects[order]
    sorted_names = tvals.index.to_numpy()[order]

    n = len(sorted_effects)
    probs = [(i - 0.5) / n for i in range(1, n + 1)]
    quantiles = stats.halfnorm.ppf(probs)

    return [
        {
            'term': str(name),
            'standardized_effect': float(effect),
            'half_normal_quantile': float(q),
        }
        for name, effect, q in zip(sorted_names, sorted_effects, quantiles, strict=True)
    ]


def run_analysis(study: Study) -> dict:
    df = build_analysis_df(study)
    factor_names = [f['name'] for f in study.factors]
    response_names = [r['name'] for r in study.responses]

    response_summaries: dict[str, dict] = {}
    for response_name in response_names:
        if response_name not in df.columns:
            continue

        local = df.dropna(subset=[response_name] + factor_names).copy()
        if len(local) < max(4, len(factor_names) + 2):
            response_summaries[response_name] = {'error': 'Not enough rows for model fitting'}
            continue

        formula = _formula(response_name, factor_names)
        model = ols(formula, data=local).fit()

        anova_df = anova_lm(model, typ=2).reset_index().rename(columns={'index': 'term'})
        anova_records = []
        for rec in anova_df.to_dict(orient='records'):
            anova_records.append(
                {
                    'term': rec.get('term'),
                    'sum_sq': float(rec.get('sum_sq', math.nan)) if pd.notna(rec.get('sum_sq')) else None,
                    'df': float(rec.get('df', math.nan)) if pd.notna(rec.get('df')) else None,
                    'f_value': float(rec.get('F', math.nan)) if pd.notna(rec.get('F')) else None,
                    'p_value': float(rec.get('PR(>F)', math.nan)) if pd.notna(rec.get('PR(>F)')) else None,
                }
            )

        significant_terms = [
            row['term']
            for row in anova_records
            if row['term'] not in ('Residual', None)
            and row['p_value'] is not None
            and row['p_value'] < P_VALUE_SIG
        ]

        residuals = model.resid
        shapiro_p = None
        if len(residuals) >= 3:
            shapiro_p = float(stats.shapiro(residuals).pvalue)

        residual_ss = float((residuals**2).sum())
        residual_df = int(model.df_resid)
        lof_p = _lack_of_fit_p(local, response_name, factor_names, residual_ss, residual_df)
        curvature_p = _curvature_p(local, response_name, study.factors)

        response_summaries[response_name] = {
            'formula': formula,
            'anova': anova_records,
            'significant_terms': significant_terms,
            'diagnostics': {
                'r_squared': float(model.rsquared),
                'adj_r_squared': float(model.rsquared_adj),
                'residual_normality_p': shapiro_p,
                'lack_of_fit_p': lof_p,
                'curvature_p': curvature_p,
            },
            'coefficients': {k: float(v) for k, v in model.params.items()},
            'half_normal_data': _half_normal(model),
        }

    return {
        'factors': factor_names,
        'responses': response_summaries,
        'n_rows': int(len(df)),
    }
