from __future__ import annotations

import json
import os
from typing import Any

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

API_BASE_URL = os.getenv('API_BASE_URL', 'http://localhost:8000')

st.set_page_config(page_title='QbD Beta', layout='wide')


def auth_headers() -> dict[str, str]:
    token = st.session_state.get('token')
    if not token:
        return {}
    return {'Authorization': f'Bearer {token}'}


def api_request(method: str, path: str, **kwargs):
    url = f'{API_BASE_URL}{path}'
    headers = kwargs.pop('headers', {})
    merged_headers = {**auth_headers(), **headers}
    resp = requests.request(method, url, headers=merged_headers, timeout=120, **kwargs)
    if resp.status_code >= 400:
        try:
            detail = resp.json()
        except Exception:  # noqa: BLE001
            detail = resp.text
        st.error(f'API Error {resp.status_code}: {detail}')
        return None
    if 'application/pdf' in resp.headers.get('content-type', ''):
        return resp.content
    if resp.text:
        return resp.json()
    return None


def login_page():
    st.title('QbD Beta 应用')
    st.caption('默认测试账号: owner@example.com / owner123')
    col1, col2 = st.columns(2)
    email = col1.text_input('邮箱', value='owner@example.com')
    password = col2.text_input('密码', type='password', value='owner123')

    if st.button('登录'):
        res = api_request('POST', '/auth/login', json={'email': email, 'password': password}, headers={})
        if res:
            st.session_state['token'] = res['access_token']
            st.success('登录成功')


def project_section():
    st.header('1) 项目管理')

    with st.expander('新建项目', expanded=False):
        name = st.text_input('项目名称', key='project_name')
        desc = st.text_input('项目描述', key='project_desc')
        if st.button('创建项目'):
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
        if st.button('添加/更新成员'):
            res = api_request(
                'POST',
                f'/projects/{project_id}/members',
                json={'user_email': member_email, 'role': role},
            )
            if res:
                st.success(f"成员更新成功: user_id={res['user_id']} role={res['role']}")

    return project_id


def study_section(project_id: int):
    st.header('2) Study 向导')

    studies = api_request('GET', f'/studies?project_id={project_id}') or []
    study_map = {f"{s['id']} - {s['name']}": s['id'] for s in studies}

    with st.expander('创建 Study', expanded=False):
        study_name = st.text_input('Study 名称', value='Formulation Study #1')
        design_type = st.selectbox('设计类型', ['full_factorial', 'fractional_factorial', 'mixture_2comp'])

        st.markdown('因子配置（JSON）')
        default_factors = [
            {'name': 'A_PSD', 'low': 10, 'high': 30, 'center': 20},
            {'name': 'B_Disintegrant', 'low': 1, 'high': 5, 'center': 3},
            {'name': 'C_MCC', 'low': 33.3, 'high': 66.7, 'center': 50},
        ]
        default_responses = [
            {'name': 'Dissolution', 'lower_bound': 80, 'upper_bound': None, 'goal': 'maximize'},
            {'name': 'CU_RSD', 'lower_bound': None, 'upper_bound': 5, 'goal': 'minimize'},
            {'name': 'Hardness', 'lower_bound': 9, 'upper_bound': None, 'goal': 'maximize'},
        ]
        factors_text = st.text_area('factors', value=json.dumps(default_factors, ensure_ascii=False, indent=2), height=180)
        responses_text = st.text_area('responses', value=json.dumps(default_responses, ensure_ascii=False, indent=2), height=180)

        if st.button('创建 Study'):
            try:
                factors = json.loads(factors_text)
                responses = json.loads(responses_text)
            except json.JSONDecodeError as exc:
                st.error(f'JSON 解析失败: {exc}')
            else:
                payload = {
                    'project_id': project_id,
                    'name': study_name,
                    'design_type': design_type,
                    'factors': factors,
                    'responses': responses,
                }
                res = api_request('POST', '/studies', json=payload)
                if res:
                    st.success(f"Study 已创建: id={res['id']}")

    studies = api_request('GET', f'/studies?project_id={project_id}') or []
    if not studies:
        st.info('暂无 Study。')
        return None

    study_map = {f"{s['id']} - {s['name']}": s['id'] for s in studies}
    selected = st.selectbox('选择 Study', list(study_map.keys()))
    study_id = study_map[selected]
    st.session_state['study_id'] = study_id
    return study_id


def doe_section(study_id: int):
    st.header('3) DOE 设计')
    c1, c2 = st.columns(2)
    center_points = c1.number_input('center points', min_value=0, max_value=20, value=3)
    fraction_p = c2.number_input('fraction p', min_value=1, max_value=3, value=1)

    if st.button('生成 DOE'):
        runs = api_request(
            'POST',
            f'/studies/{study_id}/doe/generate',
            json={'center_points': int(center_points), 'fraction_p': int(fraction_p)},
        )
        if runs:
            st.success(f'已生成 {len(runs)} 条运行')

    runs_preview = api_request('GET', f'/studies?project_id={st.session_state["project_id"]}')
    _ = runs_preview


def data_import_section(study_id: int):
    st.header('4) 结果导入')
    st.caption('CSV 至少包含 run_id 或 run_order，以及响应列')
    uploaded = st.file_uploader('上传 CSV', type=['csv'])
    if uploaded and st.button('导入结果'):
        files = {'file': (uploaded.name, uploaded.getvalue(), 'text/csv')}
        res = api_request('POST', f'/studies/{study_id}/results/import', files=files)
        if res:
            st.json(res)


def analysis_section(study_id: int):
    st.header('5) 统计分析')
    if st.button('运行分析'):
        run = api_request('POST', f'/studies/{study_id}/analysis/run')
        if run:
            st.success(f"分析任务: {run['analysis_job_id']} 状态: {run['status']}")

    summary = api_request('GET', f'/studies/{study_id}/analysis/summary')
    if not summary:
        return None

    st.subheader('ANOVA 摘要')
    st.json(summary.get('summary', {}))

    response_map = summary.get('summary', {}).get('responses', {})
    if response_map:
        response_name = st.selectbox('选择响应用于绘图', list(response_map.keys()))
        model = response_map.get(response_name, {})
        half = pd.DataFrame(model.get('half_normal_data', []))
        if not half.empty:
            fig = px.scatter(
                half,
                x='half_normal_quantile',
                y='standardized_effect',
                text='term',
                title=f'Half-normal plot: {response_name}',
            )
            st.plotly_chart(fig, use_container_width=True)

        dataset = api_request('GET', f'/studies/{study_id}/dataset') or {'rows': []}
        df = pd.DataFrame(dataset.get('rows', []))
        if not df.empty:
            factors = summary.get('summary', {}).get('factors', [])
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
                st.plotly_chart(fig_main, use_container_width=True)

            if len(factors) >= 2:
                st.subheader('交互图')
                f1 = st.selectbox('交互因子 X', factors, key='interaction_f1')
                f2 = st.selectbox('交互分组因子', factors, index=1, key='interaction_f2')
                if f1 != f2 and f1 in df.columns and f2 in df.columns and response_name in df.columns:
                    inter_df = (
                        df[[f1, f2, response_name]]
                        .groupby([f1, f2], as_index=False)
                        .mean(numeric_only=True)
                        .sort_values([f1, f2])
                    )
                    fig_inter = px.line(
                        inter_df,
                        x=f1,
                        y=response_name,
                        color=f2,
                        markers=True,
                        title=f'Interaction Plot: {f1} x {f2} -> {response_name}',
                    )
                    st.plotly_chart(fig_inter, use_container_width=True)

    return summary.get('summary', {})


def design_space_section(study_id: int, analysis_summary: dict | None):
    st.header('6) Design Space')
    if not analysis_summary:
        st.info('请先运行分析。')
        return None

    factors = analysis_summary.get('factors', [])
    if len(factors) < 2:
        st.info('至少需要两个因子。')
        return None

    c1, c2, c3 = st.columns(3)
    x_factor = c1.selectbox('X 因子', factors, index=0)
    y_factor = c2.selectbox('Y 因子', factors, index=1)
    grid_size = int(c3.number_input('网格尺寸', min_value=10, max_value=100, value=30))

    fixed = st.text_area('固定因子 JSON', value='{}', height=80)

    if st.button('生成 Design Space'):
        try:
            fixed_json = json.loads(fixed)
        except json.JSONDecodeError as exc:
            st.error(f'固定因子 JSON 错误: {exc}')
            return None

        ds = api_request(
            'POST',
            f'/studies/{study_id}/design-space/generate',
            json={
                'x_factor': x_factor,
                'y_factor': y_factor,
                'grid_size': grid_size,
                'fixed_factors': fixed_json,
            },
        )
        if ds:
            st.session_state['design_space'] = ds

    ds = st.session_state.get('design_space')
    if ds:
        matrix = pd.DataFrame(ds['pass_matrix'])
        fig = px.imshow(matrix, origin='lower', title='Overlay Pass Matrix (1=pass, 0=fail)')
        st.plotly_chart(fig, use_container_width=True)
        st.json({'feasible_ratio': ds['feasible_ratio'], 'bounds': ds['feasible_bounds']})
    return ds


def risk_section(study_id: int):
    st.header('7) 风险更新')
    default_risk = [
        {'process_step': 'Roller Compaction', 'cqa': 'Dissolution', 'risk': 'high'},
        {'process_step': 'Compression', 'cqa': 'Content Uniformity', 'risk': 'high'},
        {'process_step': 'Final Blending', 'cqa': 'Dissolution', 'risk': 'medium'},
    ]
    text = st.text_area('初始风险矩阵 JSON', value=json.dumps(default_risk, ensure_ascii=False, indent=2), height=180)
    if st.button('更新风险'):
        try:
            matrix = json.loads(text)
        except json.JSONDecodeError as exc:
            st.error(f'JSON 错误: {exc}')
            return None

        res = api_request('POST', f'/studies/{study_id}/risk/update', json={'initial_matrix': matrix})
        if res:
            st.json(res)
            st.session_state['risk'] = res
            return res
    return st.session_state.get('risk')


def control_strategy_section(study_id: int):
    st.header('8) 控制策略')
    if st.button('生成控制策略'):
        res = api_request('POST', f'/studies/{study_id}/control-strategy/generate')
        if res:
            st.session_state['control'] = res
            st.json(res)
            return res
    control = st.session_state.get('control')
    if control:
        st.json(control)
    return control


def report_section(study_id: int):
    st.header('9) 报告与审核')
    reports = api_request('GET', f'/reports?study_id={study_id}') or []
    if not reports:
        st.info('暂无报告')
        return

    report_map = {f"{r['id']} v{r['version']} ({r['status']})": r['id'] for r in reports}
    selected = st.selectbox('选择报告', list(report_map.keys()))
    report_id = report_map[selected]

    c1, c2, c3 = st.columns(3)
    if c1.button('提交审核'):
        api_request('POST', f'/reports/{report_id}/submit')
    if c2.button('批准'):
        api_request('POST', f'/reports/{report_id}/approve')
    if c3.button('驳回'):
        api_request('POST', f'/reports/{report_id}/reject')

    if st.button('导出 PDF'):
        pdf = api_request('GET', f'/reports/{report_id}/export.pdf')
        if pdf:
            st.download_button('下载报告', data=pdf, file_name=f'report-{report_id}.pdf', mime='application/pdf')


def audit_section(project_id: int):
    st.header('10) 审计日志')
    logs = api_request('GET', f'/audit-logs?project_id={project_id}') or []
    if logs:
        st.dataframe(pd.DataFrame(logs), use_container_width=True)


if 'token' not in st.session_state:
    st.session_state['token'] = None

if not st.session_state['token']:
    login_page()
else:
    st.sidebar.success('已登录')
    if st.sidebar.button('退出登录'):
        st.session_state.clear()
        st.rerun()

    project_id = project_section()
    if project_id:
        study_id = study_section(project_id)
        if study_id:
            doe_section(study_id)
            data_import_section(study_id)
            analysis_summary = analysis_section(study_id)
            design_space_section(study_id, analysis_summary)
            risk_section(study_id)
            control_strategy_section(study_id)
            report_section(study_id)
            audit_section(project_id)
