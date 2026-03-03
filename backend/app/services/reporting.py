from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from ..models import AnalysisJob, ControlStrategy, Report, RiskAssessment, Study


def _template_env() -> Environment:
    templates_dir = Path(__file__).resolve().parent.parent / 'templates'
    return Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(['html', 'xml']),
    )


def build_report_payload(study: Study, analysis: dict | None, design_space: dict | None, risk: dict | None, control: dict | None) -> dict:
    return {
        'study': {
            'id': study.id,
            'name': study.name,
            'design_type': study.design_type.value,
            'factors': study.factors,
            'responses': study.responses,
        },
        'analysis': analysis,
        'design_space': design_space,
        'risk': risk,
        'control': control,
    }


def render_report_pdf(report: Report, study: Study, payload: dict) -> bytes:
    env = _template_env()
    template = env.get_template('report.html')
    html = template.render(
        report=report,
        study=study,
        analysis=payload.get('analysis'),
        design_space=payload.get('design_space'),
        risk=payload.get('risk'),
        control=payload.get('control'),
    )
    return HTML(string=html).write_pdf()


def latest_analysis(study: Study) -> AnalysisJob | None:
    if not study.analysis_jobs:
        return None
    return sorted(study.analysis_jobs, key=lambda x: x.created_at or 0, reverse=True)[0]


def latest_risk(study_id: int, risks: list[RiskAssessment]) -> RiskAssessment | None:
    entries = [r for r in risks if r.study_id == study_id and r.phase == 'updated']
    if not entries:
        return None
    return sorted(entries, key=lambda x: x.created_at or 0, reverse=True)[0]


def latest_control(study_id: int, controls: list[ControlStrategy]) -> ControlStrategy | None:
    entries = [c for c in controls if c.study_id == study_id]
    if not entries:
        return None
    return sorted(entries, key=lambda x: x.created_at or 0, reverse=True)[0]
