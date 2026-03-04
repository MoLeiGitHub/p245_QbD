from __future__ import annotations

import json
import os
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

API_BASE_URL = os.getenv('API_BASE_URL', 'http://localhost:18101')

st.set_page_config(page_title='QbD Beta', layout='wide')


def apply_app_style() -> None:
    st.markdown(
        """
        <style>
          .block-container { max-width: 1400px; }
          .qbd-note {
            padding: 0.9rem 1rem;
            border: 1px solid #dbe4f0;
            border-radius: 10px;
            background: #f8fbff;
            margin-bottom: 0.8rem;
          }
          .qbd-step {
            font-weight: 700;
            color: #0b3b75;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def auth_headers() -> dict[str, str]:
    token = st.session_state.get('token')
    if not token:
        return {}
    return {'Authorization': f'Bearer {token}'}


def api_request(method: str, path: str, **kwargs):
    quiet = kwargs.pop('quiet', False)
    allow_statuses = set(kwargs.pop('allow_statuses', []))
    url = f'{API_BASE_URL}{path}'
    headers = kwargs.pop('headers', {})
    merged_headers = {**auth_headers(), **headers}
    resp = requests.request(method, url, headers=merged_headers, timeout=180, **kwargs)

    if resp.status_code in allow_statuses:
        return None

    if resp.status_code >= 400:
        try:
            detail = resp.json()
        except Exception:  # noqa: BLE001
            detail = resp.text
        if not quiet:
            st.error(f'API Error {resp.status_code}: {detail}')
        return None

    content_type = resp.headers.get('content-type', '')
    if 'application/pdf' in content_type or 'text/csv' in content_type:
        return resp.content
    if 'application/json' in content_type:
        return resp.json()

    if resp.text:
        try:
            return resp.json()
        except Exception:  # noqa: BLE001
            return resp.text
    return None


def status_chip(done: bool) -> str:
    return '✅' if done else '⬜'


def to_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == '':
        return None
    if pd.isna(value):
        return None
    return float(value)


FACTORIAL_FACTORS = [
    {'name': 'A_PSD', 'low': 10.0, 'high': 30.0, 'center': 20.0},
    {'name': 'B_Disintegrant', 'low': 1.0, 'high': 5.0, 'center': 3.0},
    {'name': 'C_MCC', 'low': 33.3, 'high': 66.7, 'center': 50.0},
]

MIXTURE_FACTORS = [
    {'name': 'A_MgStearate', 'low': 0.0, 'high': 1.0, 'center': 0.5},
    {'name': 'B_Talc', 'low': 0.0, 'high': 1.0, 'center': 0.5},
]

DEFAULT_RESPONSES = [
    {'name': 'Dissolution', 'lower_bound': 80.0, 'upper_bound': None, 'goal': 'maximize'},
    {'name': 'CU_RSD', 'lower_bound': None, 'upper_bound': 5.0, 'goal': 'minimize'},
    {'name': 'Hardness', 'lower_bound': 9.0, 'upper_bound': None, 'goal': 'maximize'},
]

DEFAULT_RISK_ROWS = [
    {'process_step': 'Roller Compaction', 'cqa': 'Dissolution', 'risk': 'high'},
    {'process_step': 'Compression', 'cqa': 'Content Uniformity', 'risk': 'high'},
    {'process_step': 'Final Blending', 'cqa': 'Dissolution', 'risk': 'medium'},
]


def login_page():
    st.title('QbD Beta 应用')
    st.caption('默认账号：owner@example.com / owner123')

    with st.container(border=True):
        col1, col2 = st.columns(2)
        email = col1.text_input('邮箱', value='owner@example.com')
        password = col2.text_input('密码', type='password', value='owner123')

        if st.button('登录', type='primary'):
            res = api_request('POST', '/auth/login', json={'email': email, 'password': password}, headers={})
            if res:
                st.session_state['token'] = res['access_token']
                st.success('登录成功')
                st.rerun()


def quick_guide_panel() -> None:
    with st.expander('小白快速上手（2分钟）', expanded=True):
        st.markdown(
            """
            1. 新建项目 -> 新建 Study（建议先选 `full_factorial`）。
            2. 点击“生成 DOE”。
            3. 点击“下载结果模板 CSV”，把实验结果填进去后上传导入。
            4. 点击“运行分析”，查看 ANOVA/半正态图/主效应图。
            5. 进入 Design Space，选择 X/Y 因子并固定剩余因子后生成叠加图。
            6. 更新风险 -> 生成控制策略 -> 提交/审核报告 -> 导出 PDF。
            """
        )


def project_section() -> int | None:
    st.header('1) 项目管理')

    with st.expander('新建项目', expanded=False):
        name = st.text_input('项目名称', key='project_name')
        desc = st.text_input('项目描述', key='project_desc')
        if st.button('创建项目', key='create_project_btn'):
            created = api_request('POST', '/projects', json={'name': name, 'description': desc})
            if created:
                st.success(f"项目已创建: {created['name']} (id={created['id']})")

    projects = api_request('GET', '/projects') or []
    if not projects:
        st.info('暂无项目，请先创建。')
        return None

    project_map = {f"{p['id']} - {p['name']}": p['id'] for p in projects}
    selected = st.selectbox('选择项目', list(project_map.keys()))
    project_id = project_map[selected]
    st.session_state['project_id'] = project_id

    with st.expander('成员管理（Owner）', expanded=False):
        member_email = st.text_input('成员邮箱', key='member_email')
        role = st.selectbox('角色', ['owner', 'editor', 'reviewer', 'viewer'], key='member_role')
        if st.button('添加/更新成员', key='upsert_member_btn'):
            res = api_request(
                'POST',
                f'/projects/{project_id}/members',
                json={'user_email': member_email, 'role': role},
            )
            if res:
                st.success(f"成员更新成功: user_id={res['user_id']} role={res['role']}")

    return project_id


def render_workflow_status(study: dict) -> None:
    study_id = study['id']
    runs = api_request('GET', f'/studies/{study_id}/runs', quiet=True, allow_statuses=[404]) or []
    dataset = api_request('GET', f'/studies/{study_id}/dataset', quiet=True, allow_statuses=[404]) or {'rows': []}
    analysis = api_request('GET', f'/studies/{study_id}/analysis/summary', quiet=True, allow_statuses=[404])
    reports = api_request('GET', f'/reports?study_id={study_id}', quiet=True, allow_statuses=[404]) or []

    ds_ready = f'design_space_{study_id}' in st.session_state
    risk_ready = f'risk_result_{study_id}' in st.session_state
    control_ready = f'control_{study_id}' in st.session_state
    report_status = reports[0]['status'] if reports else None

    analysis_done = bool(analysis and analysis.get('status') == 'done')
    analysis_failed = bool(analysis and analysis.get('status') == 'failed')

    st.sidebar.markdown('### 流程状态')
    st.sidebar.write(f"{status_chip(len(runs) > 0)} DOE 已生成")
    st.sidebar.write(f"{status_chip(len(dataset.get('rows', [])) > 0)} 结果已导入")
    if analysis_failed:
        st.sidebar.write('⚠️ 分析失败（请看页面错误原因）')
    else:
        st.sidebar.write(f"{status_chip(analysis_done)} 分析已完成")
    st.sidebar.write(f"{status_chip(ds_ready)} Design Space 已生成")
    st.sidebar.write(f"{status_chip(risk_ready)} 风险已更新")
    st.sidebar.write(f"{status_chip(control_ready)} 控制策略已生成")
    st.sidebar.write(f"{status_chip(report_status == 'approved')} 报告已批准")


def _init_study_editor_state(design_type: str) -> None:
    key_design = 'study_editor_design_type'
    key_factors = 'study_editor_factors'
    key_responses = 'study_editor_responses'

    if design_type == 'mixture_2comp':
        factors = MIXTURE_FACTORS
    else:
        factors = FACTORIAL_FACTORS

    if st.session_state.get(key_design) != design_type:
        st.session_state[key_design] = design_type
        st.session_state[key_factors] = pd.DataFrame(factors)
        st.session_state[key_responses] = pd.DataFrame(DEFAULT_RESPONSES)



def _serialize_factors(factor_df: pd.DataFrame, design_type: str) -> tuple[list[dict], list[str]]:
    errors: list[str] = []
    factors: list[dict] = []

    for idx, row in factor_df.iterrows():
        name = str(row.get('name', '')).strip()
        if not name:
            continue

        low = to_optional_float(row.get('low'))
        high = to_optional_float(row.get('high'))
        center = to_optional_float(row.get('center'))

        if low is None or high is None:
            errors.append(f'因子第 {idx + 1} 行缺少 low/high。')
            continue
        if low >= high:
            errors.append(f'因子 {name} 的 low 必须小于 high。')
            continue

        factor = {'name': name, 'low': low, 'high': high}
        if center is not None:
            factor['center'] = center
        factors.append(factor)

    if not factors:
        errors.append('至少需要 1 个因子。')

    if design_type == 'mixture_2comp' and len(factors) != 2:
        errors.append('mixture_2comp 必须且只能有 2 个因子。')
    if design_type in ('full_factorial', 'fractional_factorial') and len(factors) < 2:
        errors.append('factorial 设计至少需要 2 个因子。')

    return factors, errors



def _serialize_responses(response_df: pd.DataFrame) -> tuple[list[dict], list[str]]:
    errors: list[str] = []
    responses: list[dict] = []

    for idx, row in response_df.iterrows():
        name = str(row.get('name', '')).strip()
        if not name:
            continue

        goal = str(row.get('goal', 'target')).strip() or 'target'
        if goal not in ('maximize', 'minimize', 'target'):
            errors.append(f'响应 {name} 的 goal 必须是 maximize/minimize/target。')
            continue

        lower_bound = to_optional_float(row.get('lower_bound'))
        upper_bound = to_optional_float(row.get('upper_bound'))

        if lower_bound is not None and upper_bound is not None and lower_bound > upper_bound:
            errors.append(f'响应 {name} 的 lower_bound 不能大于 upper_bound。')
            continue

        responses.append(
            {
                'name': name,
                'lower_bound': lower_bound,
                'upper_bound': upper_bound,
                'goal': goal,
            }
        )

    if not responses:
        errors.append('至少需要 1 个响应。')

    return responses, errors


def study_section(project_id: int) -> dict | None:
    st.header('2) Study 向导')

    with st.expander('创建 Study（表单模式）', expanded=False):
        study_name = st.text_input('Study 名称', value='Formulation Study #1', key='study_name_input')
        design_type = st.selectbox(
            '设计类型',
            ['full_factorial', 'fractional_factorial', 'mixture_2comp'],
            key='study_design_select',
        )

        _init_study_editor_state(design_type)

        c1, c2 = st.columns([3, 1])
        c1.markdown('<div class="qbd-step">步骤A：配置因子</div>', unsafe_allow_html=True)
        if c2.button('恢复推荐模板', key='reset_study_template'):
            st.session_state['study_editor_design_type'] = None
            _init_study_editor_state(design_type)
            st.rerun()

        factor_df = st.data_editor(
            st.session_state['study_editor_factors'],
            num_rows='dynamic',
            use_container_width=True,
            column_config={
                'name': st.column_config.TextColumn('name'),
                'low': st.column_config.NumberColumn('low', format='%.4f'),
                'high': st.column_config.NumberColumn('high', format='%.4f'),
                'center': st.column_config.NumberColumn('center', format='%.4f'),
            },
            hide_index=True,
        )
        st.session_state['study_editor_factors'] = factor_df

        st.markdown('<div class="qbd-step">步骤B：配置响应</div>', unsafe_allow_html=True)
        response_df = st.data_editor(
            st.session_state['study_editor_responses'],
            num_rows='dynamic',
            use_container_width=True,
            column_config={
                'name': st.column_config.TextColumn('name'),
                'lower_bound': st.column_config.NumberColumn('lower_bound', format='%.4f'),
                'upper_bound': st.column_config.NumberColumn('upper_bound', format='%.4f'),
                'goal': st.column_config.SelectboxColumn('goal', options=['maximize', 'minimize', 'target']),
            },
            hide_index=True,
        )
        st.session_state['study_editor_responses'] = response_df

        if st.button('创建 Study', key='create_study_btn', type='primary'):
            factors, factor_errors = _serialize_factors(factor_df, design_type)
            responses, response_errors = _serialize_responses(response_df)
            errors = factor_errors + response_errors

            if not study_name.strip():
                errors.append('Study 名称不能为空。')

            if errors:
                for err in errors:
                    st.error(err)
            else:
                payload = {
                    'project_id': project_id,
                    'name': study_name.strip(),
                    'design_type': design_type,
                    'factors': factors,
                    'responses': responses,
                }
                res = api_request('POST', '/studies', json=payload)
                if res:
                    st.success(f"Study 已创建: id={res['id']}")
                    st.rerun()

    studies = api_request('GET', f'/studies?project_id={project_id}') or []
    if not studies:
        st.info('暂无 Study。')
        return None

    study_map = {f"{s['id']} - {s['name']} ({s['design_type']})": s for s in studies}
    selected = st.selectbox('选择 Study', list(study_map.keys()))
    selected_study = study_map[selected]
    st.session_state['study_id'] = selected_study['id']

    with st.container(border=True):
        st.caption('当前 Study 概览')
        c1, c2, c3 = st.columns(3)
        c1.metric('Design Type', selected_study['design_type'])
        c2.metric('因素数量', len(selected_study.get('factors', [])))
        c3.metric('响应数量', len(selected_study.get('responses', [])))

    return selected_study


def doe_section(study: dict):
    study_id = study['id']
    st.header('3) DOE 设计')

    c1, c2 = st.columns(2)
    center_points = c1.number_input('center points', min_value=0, max_value=20, value=3)

    if study['design_type'] == 'fractional_factorial':
        fraction_p = c2.number_input('fraction p', min_value=1, max_value=3, value=1)
    else:
        fraction_p = 1
        c2.number_input('fraction p（仅分数因子使用）', min_value=1, max_value=3, value=1, disabled=True)

    if st.button('生成 DOE', key='generate_doe_btn', type='primary'):
        runs = api_request(
            'POST',
            f'/studies/{study_id}/doe/generate',
            json={'center_points': int(center_points), 'fraction_p': int(fraction_p)},
        )
        if runs is not None:
            st.success(f'已生成 {len(runs)} 条运行')

    runs = api_request('GET', f'/studies/{study_id}/runs') or []
    if not runs:
        st.info('还没有 DOE 运行，请先点击“生成 DOE”。')
        return

    run_df = pd.DataFrame(runs)
    factor_cols = sorted({k for row in run_df.get('factor_values', []) for k in row.keys()})
    if factor_cols:
        expanded_rows = []
        for _, row in run_df.iterrows():
            r = {'run_order': row['run_order']}
            for f in factor_cols:
                r[f] = row['factor_values'].get(f)
            expanded_rows.append(r)
        show_df = pd.DataFrame(expanded_rows)
    else:
        show_df = run_df[['run_order']]

    with st.expander('查看 DOE 运行矩阵', expanded=False):
        st.dataframe(show_df, use_container_width=True)


def data_import_section(study: dict):
    study_id = study['id']
    st.header('4) 结果导入')
    st.caption('推荐流程：先下载模板 -> 填值 -> 上传导入')

    template_bytes = api_request('GET', f'/studies/{study_id}/results/template.csv')
    if template_bytes:
        st.download_button(
            '下载当前 Study 导入模板 CSV',
            data=template_bytes,
            file_name=f'study-{study_id}-results-template.csv',
            mime='text/csv',
        )

    with st.expander('响应列要求（必须与 Study 一致）', expanded=False):
        st.write([r['name'] for r in study.get('responses', [])])

    uploaded = st.file_uploader('上传 CSV', type=['csv'])
    if uploaded:
        preview_df = pd.read_csv(uploaded)
        st.dataframe(preview_df.head(8), use_container_width=True)

    if uploaded and st.button('导入结果', key='import_results_btn', type='primary'):
        files = {'file': (uploaded.name, uploaded.getvalue(), 'text/csv')}
        res = api_request('POST', f'/studies/{study_id}/results/import', files=files)
        if res:
            imported_runs = int(res.get('imported_runs', 0))
            if imported_runs <= 0:
                st.error('未匹配到任何 run。请检查 run_order/run_id 是否与当前 Study 的 DOE 一致。')
            else:
                st.success(f'导入成功：{imported_runs} 条')

            if res.get('threshold_flags'):
                st.warning(f"检测到 {len(res['threshold_flags'])} 条阈值超限（用于提示，不阻断分析）。")
            st.json(res)


def style_figure(fig: go.Figure) -> go.Figure:
    fig.update_layout(
        template='plotly_white',
        font=dict(family='Arial', size=13, color='#1f2937'),
        title_font=dict(size=18, color='#0f172a'),
        margin=dict(l=40, r=30, t=70, b=50),
        legend_title_text='',
    )
    fig.update_xaxes(showline=True, linewidth=1, linecolor='#cbd5e1', mirror=True)
    fig.update_yaxes(showline=True, linewidth=1, linecolor='#cbd5e1', mirror=True)
    return fig


def analysis_section(study: dict):
    study_id = study['id']
    st.header('5) 统计分析')

    if st.button('运行分析', key='run_analysis_btn', type='primary'):
        run = api_request('POST', f'/studies/{study_id}/analysis/run')
        if run:
            if run['status'] == 'failed':
                st.error(f"分析任务: {run['analysis_job_id']} failed\n原因: {run.get('error_message') or '未知错误'}")
            else:
                st.success(f"分析任务: {run['analysis_job_id']} 状态: {run['status']}")

    summary_resp = api_request('GET', f'/studies/{study_id}/analysis/summary', quiet=True, allow_statuses=[404])
    if not summary_resp:
        st.info('还没有分析结果。')
        return None

    if summary_resp.get('status') == 'failed':
        st.error(f"最近一次分析失败：{summary_resp.get('error_message') or '未知错误'}")
        return None

    summary = summary_resp.get('summary', {})
    response_map = summary.get('responses', {})
    if not response_map:
        st.warning('当前分析没有可展示的响应模型。')
        return summary

    response_name = st.selectbox('选择响应', list(response_map.keys()), key='analysis_response_name')
    model = response_map.get(response_name, {})

    diag = model.get('diagnostics', {})
    c1, c2, c3, c4 = st.columns(4)
    c1.metric('R²', f"{diag.get('r_squared', 0):.4f}")
    c2.metric('Adj R²', f"{diag.get('adj_r_squared', 0):.4f}")
    c3.metric('Shapiro p', f"{(diag.get('residual_normality_p') or 0):.4f}")
    c4.metric('Lack-of-fit p', f"{(diag.get('lack_of_fit_p') or 0):.4f}")

    anova_df = pd.DataFrame(model.get('anova', []))
    if not anova_df.empty:
        anova_df['significant'] = anova_df['p_value'].apply(
            lambda v: 'Yes' if (v is not None and not pd.isna(v) and float(v) < 0.05) else 'No'
        )
        with st.expander('ANOVA 表', expanded=False):
            st.dataframe(anova_df, use_container_width=True)

    half = pd.DataFrame(model.get('half_normal_data', []))
    if not half.empty:
        half = half.sort_values('standardized_effect').reset_index(drop=True)
        half['probability_pct'] = 100 * (np.arange(1, len(half) + 1) - 0.5) / len(half)

        x = half['standardized_effect'].to_numpy(dtype=float)
        y = half['probability_pct'].to_numpy(dtype=float)
        coef = np.polyfit(x, y, 1)
        yhat = coef[0] * x + coef[1]

        fig_half = go.Figure()
        fig_half.add_trace(
            go.Scatter(
                x=x,
                y=y,
                mode='markers+text',
                text=half['term'],
                textposition='top center',
                marker=dict(size=10, color='#1d4ed8', line=dict(color='white', width=1)),
                name='Effects',
            )
        )
        fig_half.add_trace(
            go.Scatter(
                x=x,
                y=yhat,
                mode='lines',
                line=dict(color='#dc2626', dash='dash'),
                name='Reference',
            )
        )
        fig_half.update_layout(title=f'Half-Normal Plot ({response_name})')
        fig_half.update_xaxes(title='|Standardized Effect|')
        fig_half.update_yaxes(title='Half-Normal Probability (%)')
        st.plotly_chart(style_figure(fig_half), use_container_width=True)

    dataset = api_request('GET', f'/studies/{study_id}/dataset') or {'rows': []}
    df = pd.DataFrame(dataset.get('rows', []))
    if df.empty:
        return summary

    factors = summary.get('factors', [])

    st.subheader('主效应图')
    factor_for_main = st.selectbox('主效应因子', factors, key='main_effect_factor')
    if factor_for_main in df.columns and response_name in df.columns:
        main_df = (
            df[[factor_for_main, response_name]]
            .groupby(factor_for_main, as_index=False)
            .mean(numeric_only=True)
            .sort_values(factor_for_main)
        )
        fig_main = px.line(
            main_df,
            x=factor_for_main,
            y=response_name,
            markers=True,
            title=f'Main Effect: {factor_for_main} -> {response_name}',
        )
        fig_main.update_traces(line=dict(color='#0f766e', width=3), marker=dict(size=8))
        st.plotly_chart(style_figure(fig_main), use_container_width=True)

    if len(factors) >= 2:
        st.subheader('交互图')
        c1, c2 = st.columns(2)
        f1 = c1.selectbox('交互因子 X', factors, key='interaction_f1')
        f2_candidates = [f for f in factors if f != f1]
        f2 = c2.selectbox('交互分组因子', f2_candidates, key='interaction_f2')

        if f1 in df.columns and f2 in df.columns and response_name in df.columns:
            inter_df = (
                df[[f1, f2, response_name]].groupby([f1, f2], as_index=False).mean(numeric_only=True).sort_values([f1, f2])
            )
            fig_inter = px.line(
                inter_df,
                x=f1,
                y=response_name,
                color=f2,
                markers=True,
                title=f'Interaction: {f1} x {f2} -> {response_name}',
            )
            fig_inter.update_traces(line=dict(width=2.5), marker=dict(size=8))
            st.plotly_chart(style_figure(fig_inter), use_container_width=True)

    return summary


def design_space_section(study: dict, analysis_summary: dict | None):
    st.header('6) Design Space')
    if not analysis_summary:
        st.info('请先运行分析。')
        return None

    factors = analysis_summary.get('factors', [])
    if len(factors) < 2:
        st.info('至少需要两个因子。')
        return None

    factor_specs = {f['name']: f for f in study.get('factors', [])}

    c1, c2, c3 = st.columns(3)
    x_factor = c1.selectbox('X 因子', factors, index=0, key='ds_x_factor')

    y_candidates = [f for f in factors if f != x_factor]
    y_factor = c2.selectbox('Y 因子', y_candidates, index=0, key='ds_y_factor')
    grid_size = int(c3.number_input('网格尺寸', min_value=10, max_value=100, value=30, key='ds_grid_size'))

    st.markdown('固定其他因子（不需要写 JSON，直接填数值）')
    fixed_factors: dict[str, float] = {}
    other_factors = [f for f in factors if f not in (x_factor, y_factor)]
    if other_factors:
        cols = st.columns(min(3, len(other_factors)))
        for idx, fac in enumerate(other_factors):
            spec = factor_specs.get(fac, {})
            default = float(spec.get('center', (spec.get('low', 0) + spec.get('high', 1)) / 2))
            fixed_factors[fac] = cols[idx % len(cols)].number_input(
                f'{fac}',
                value=default,
                key=f'ds_fixed_{fac}',
            )
    else:
        st.caption('当前只有两个因子，无需固定其他因子。')

    if st.button('生成 Design Space', key='generate_ds_btn', type='primary'):
        ds = api_request(
            'POST',
            f"/studies/{study['id']}/design-space/generate",
            json={
                'x_factor': x_factor,
                'y_factor': y_factor,
                'grid_size': grid_size,
                'fixed_factors': fixed_factors,
            },
        )
        if ds:
            st.session_state[f'design_space_{study["id"]}'] = ds

    ds = st.session_state.get(f'design_space_{study["id"]}')
    if not ds:
        return None

    feasible_ratio = float(ds.get('feasible_ratio', 0.0))
    c1, c2 = st.columns([1, 3])
    c1.metric('可行域占比', f'{feasible_ratio * 100:.2f}%')
    if feasible_ratio < 0.2:
        c2.warning('可行域较小，建议调整固定因子或响应阈值后重算。')
    else:
        c2.info('绿色区域表示该参数组合下，所有响应均满足阈值要求。')

    matrix = np.array(ds['pass_matrix'])
    x_spec = factor_specs.get(x_factor, {'low': 0, 'high': matrix.shape[1] - 1})
    y_spec = factor_specs.get(y_factor, {'low': 0, 'high': matrix.shape[0] - 1})
    x_vals = np.linspace(float(x_spec['low']), float(x_spec['high']), matrix.shape[1])
    y_vals = np.linspace(float(y_spec['low']), float(y_spec['high']), matrix.shape[0])

    fig_overlay = go.Figure(
        data=
        go.Heatmap(
            x=x_vals,
            y=y_vals,
            z=matrix,
            colorscale=[
                [0.0, '#e5e7eb'],
                [0.49, '#e5e7eb'],
                [0.5, '#2f9e44'],
                [1.0, '#2f9e44'],
            ],
            zmin=0,
            zmax=1,
            colorbar=dict(title='Feasible', tickvals=[0, 1], ticktext=['No', 'Yes']),
            hovertemplate=f'{x_factor}: %{{x:.3f}}<br>{y_factor}: %{{y:.3f}}<br>Pass: %{{z}}<extra></extra>',
        )
    )
    fig_overlay.update_layout(title='Overlay Plot (Green Zone = all responses pass)')
    fig_overlay.update_xaxes(title=x_factor)
    fig_overlay.update_yaxes(title=y_factor)
    st.plotly_chart(style_figure(fig_overlay), use_container_width=True)
    st.json({'feasible_bounds': ds.get('feasible_bounds'), 'fixed_factors': ds.get('fixed_factors')})

    predictions = ds.get('predictions', [])
    pred_df = pd.DataFrame(predictions)
    if pred_df.empty or 'predictions' not in pred_df.columns:
        return ds

    response_candidates = [r['name'] for r in study.get('responses', [])]
    response_for_surface = st.selectbox(
        '响应面响应变量',
        response_candidates,
        key=f"surface_response_{study['id']}",
    )

    pred_df[response_for_surface] = pred_df['predictions'].apply(
        lambda d: d.get(response_for_surface) if isinstance(d, dict) else np.nan
    )
    pred_df = pred_df.dropna(subset=[x_factor, y_factor, response_for_surface])
    if pred_df.empty:
        st.warning('当前响应没有可用于响应面绘制的预测值。')
        return ds

    grid = (
        pred_df.pivot_table(
            index=y_factor,
            columns=x_factor,
            values=response_for_surface,
            aggfunc='mean',
        )
        .sort_index()
        .sort_index(axis=1)
    )
    if grid.empty:
        st.warning('无法生成响应面网格。')
        return ds

    xg = grid.columns.to_numpy(dtype=float)
    yg = grid.index.to_numpy(dtype=float)
    zg = grid.to_numpy(dtype=float)

    tab_surface, tab_contour = st.tabs(['3D 响应面', '2D 等高线'])
    with tab_surface:
        fig_surface = go.Figure(
            data=[
                go.Surface(
                    x=xg,
                    y=yg,
                    z=zg,
                    colorscale='Viridis',
                    colorbar=dict(title=response_for_surface),
                )
            ]
        )
        fig_surface.update_layout(
            title=f'Response Surface: {response_for_surface}',
            scene=dict(
                xaxis_title=x_factor,
                yaxis_title=y_factor,
                zaxis_title=response_for_surface,
            ),
        )
        st.plotly_chart(style_figure(fig_surface), use_container_width=True)

    with tab_contour:
        fig_contour = go.Figure(
            data=[
                go.Contour(
                    x=xg,
                    y=yg,
                    z=zg,
                    colorscale='Viridis',
                    contours=dict(showlabels=True, labelfont=dict(size=11, color='white')),
                    colorbar=dict(title=response_for_surface),
                )
            ]
        )
        fig_contour.update_layout(title=f'Contour Plot: {response_for_surface}')
        fig_contour.update_xaxes(title=x_factor)
        fig_contour.update_yaxes(title=y_factor)
        st.plotly_chart(style_figure(fig_contour), use_container_width=True)

    return ds


def risk_section(study: dict):
    st.header('7) 风险更新')
    key = f'risk_editor_{study["id"]}'
    if key not in st.session_state:
        st.session_state[key] = pd.DataFrame(DEFAULT_RISK_ROWS)

    risk_df = st.data_editor(
        st.session_state[key],
        num_rows='dynamic',
        use_container_width=True,
        column_config={
            'process_step': st.column_config.TextColumn('process_step'),
            'cqa': st.column_config.TextColumn('cqa'),
            'risk': st.column_config.SelectboxColumn('risk', options=['low', 'medium', 'high']),
        },
        hide_index=True,
    )
    st.session_state[key] = risk_df

    if st.button('更新风险', key='update_risk_btn', type='primary'):
        rows = []
        for _, row in risk_df.iterrows():
            process_step = str(row.get('process_step', '')).strip()
            cqa = str(row.get('cqa', '')).strip()
            risk = str(row.get('risk', '')).strip().lower()
            if not process_step or not cqa or risk not in ('low', 'medium', 'high'):
                continue
            rows.append({'process_step': process_step, 'cqa': cqa, 'risk': risk})

        if not rows:
            st.error('请至少填写一行有效风险记录。')
            return None

        res = api_request('POST', f"/studies/{study['id']}/risk/update", json={'initial_matrix': rows})
        if res:
            st.success('风险更新完成')
            st.session_state[f'risk_result_{study["id"]}'] = res

    result = st.session_state.get(f'risk_result_{study["id"]}')
    if result:
        st.write('更新结果')
        c1, c2 = st.columns(2)
        c1.dataframe(pd.DataFrame(result.get('initial', [])), use_container_width=True)
        c2.dataframe(pd.DataFrame(result.get('updated', [])), use_container_width=True)
        st.info(result.get('rationale', ''))
    return result


def control_strategy_section(study: dict):
    st.header('8) 控制策略')
    if st.button('生成控制策略', key='generate_control_btn', type='primary'):
        res = api_request('POST', f"/studies/{study['id']}/control-strategy/generate")
        if res:
            st.session_state[f'control_{study["id"]}'] = res
            st.success('控制策略已生成')

    control = st.session_state.get(f'control_{study["id"]}')
    if control:
        strategy = control.get('strategy', {})
        fc = pd.DataFrame(strategy.get('factor_controls', []))
        if not fc.empty:
            st.dataframe(fc, use_container_width=True)
        else:
            st.json(control)
    return control


def report_section(study: dict):
    st.header('9) 报告与审核')
    reports = api_request('GET', f"/reports?study_id={study['id']}") or []
    if not reports:
        st.info('暂无报告')
        return

    report_map = {f"{r['id']} v{r['version']} ({r['status']})": r['id'] for r in reports}
    selected = st.selectbox('选择报告', list(report_map.keys()))
    report_id = report_map[selected]

    c1, c2, c3 = st.columns(3)
    if c1.button('提交审核', key='report_submit_btn'):
        api_request('POST', f'/reports/{report_id}/submit')
    if c2.button('批准', key='report_approve_btn'):
        api_request('POST', f'/reports/{report_id}/approve')
    if c3.button('驳回', key='report_reject_btn'):
        api_request('POST', f'/reports/{report_id}/reject')

    if st.button('导出 PDF', key='report_export_btn', type='primary'):
        pdf = api_request('GET', f'/reports/{report_id}/export.pdf')
        if pdf:
            st.download_button('下载报告文件', data=pdf, file_name=f'report-{report_id}.pdf', mime='application/pdf')


def audit_section(project_id: int):
    st.header('10) 审计日志')
    logs = api_request('GET', f'/audit-logs?project_id={project_id}') or []
    if logs:
        st.dataframe(pd.DataFrame(logs), use_container_width=True)


def main() -> None:
    apply_app_style()

    if 'token' not in st.session_state:
        st.session_state['token'] = None

    if not st.session_state['token']:
        login_page()
        return

    st.sidebar.success('已登录')
    st.sidebar.caption(f'API: {API_BASE_URL}')
    if st.sidebar.button('退出登录'):
        st.session_state.clear()
        st.rerun()

    quick_guide_panel()
    project_id = project_section()
    if not project_id:
        return

    study = study_section(project_id)
    if not study:
        return
    render_workflow_status(study)

    doe_section(study)
    data_import_section(study)
    analysis_summary = analysis_section(study)
    design_space_section(study, analysis_summary)
    risk_section(study)
    control_strategy_section(study)
    report_section(study)
    audit_section(project_id)


if __name__ == '__main__':
    main()
