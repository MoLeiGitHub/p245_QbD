from __future__ import annotations

RISK_ORDER = ['low', 'medium', 'high']


def _downgrade(risk: str) -> str:
    risk_l = risk.lower()
    if risk_l == 'high':
        return 'medium'
    if risk_l == 'medium':
        return 'low'
    return risk_l


def update_risk_matrix(initial_matrix: list[dict], feasible_ratio: float, has_significant_terms: bool) -> tuple[list[dict], str]:
    updated = []
    for row in initial_matrix:
        new_row = row.copy()
        risk = str(row.get('risk', 'medium')).lower()
        if feasible_ratio > 0 and has_significant_terms:
            new_row['risk'] = _downgrade(risk)
            new_row['reason'] = 'Model-backed operating space identified and controls proposed.'
        elif feasible_ratio > 0:
            new_row['risk'] = _downgrade(risk)
            new_row['reason'] = 'Feasible design space found.'
        else:
            new_row['risk'] = risk
            new_row['reason'] = 'No feasible design space; keep current risk.'
        updated.append(new_row)

    if feasible_ratio > 0:
        rationale = 'Risk reduced using analysis evidence and feasible design space.'
    else:
        rationale = 'Risk unchanged due to insufficient feasible design space evidence.'
    return updated, rationale
