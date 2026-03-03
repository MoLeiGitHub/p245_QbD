from __future__ import annotations

from ..models import Study


def generate_control_strategy(study: Study, analysis_summary: dict, design_space: dict | None = None) -> dict:
    factor_controls = []
    bounds = (design_space or {}).get('feasible_bounds', {})

    for factor in study.factors:
        name = factor['name']
        proposed = bounds.get(name) if bounds else None
        if not proposed:
            proposed = {'min': float(factor['low']), 'max': float(factor['high'])}

        factor_controls.append(
            {
                'factor': name,
                'type': 'CPP/CMA candidate',
                'studied_range': {'min': float(factor['low']), 'max': float(factor['high'])},
                'proposed_range': proposed,
                'purpose': 'Maintain response targets and process robustness.',
            }
        )

    response_controls = []
    for response in study.responses:
        response_controls.append(
            {
                'response': response['name'],
                'lower_bound': response.get('lower_bound'),
                'upper_bound': response.get('upper_bound'),
                'goal': response.get('goal', 'target'),
            }
        )

    significant_summary = {
        name: model.get('significant_terms', [])
        for name, model in analysis_summary.get('responses', {}).items()
    }

    return {
        'factor_controls': factor_controls,
        'response_controls': response_controls,
        'analysis_significant_terms': significant_summary,
        'in_process_controls': [
            {'name': 'Blend Uniformity', 'rule': '%RSD < 5%'},
            {'name': 'Tablet Hardness', 'rule': 'Target range managed per design space'},
        ],
    }
