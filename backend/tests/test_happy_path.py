import os

# Set test DB before importing app modules.
os.environ['DATABASE_URL'] = 'sqlite:///./test_qbd.db'
os.environ['SECRET_KEY'] = 'test-secret'

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _token(email='owner@example.com', password='owner123'):
    res = client.post('/auth/login', json={'email': email, 'password': password})
    assert res.status_code == 200
    return res.json()['access_token']


def test_end_to_end_happy_path():
    token = _token()
    headers = {'Authorization': f'Bearer {token}'}

    project = client.post('/projects', json={'name': 'Demo', 'description': 'demo'}, headers=headers)
    assert project.status_code == 200
    project_id = project.json()['id']

    study_payload = {
        'project_id': project_id,
        'name': 'Study1',
        'design_type': 'full_factorial',
        'factors': [
            {'name': 'A', 'low': 10, 'high': 30, 'center': 20},
            {'name': 'B', 'low': 1, 'high': 5, 'center': 3},
        ],
        'responses': [
            {'name': 'Dissolution', 'lower_bound': 80, 'upper_bound': None, 'goal': 'maximize'},
            {'name': 'CU_RSD', 'lower_bound': None, 'upper_bound': 5, 'goal': 'minimize'},
        ],
    }
    study = client.post('/studies', json=study_payload, headers=headers)
    assert study.status_code == 200
    study_id = study.json()['id']

    doe = client.post(
        f'/studies/{study_id}/doe/generate',
        json={'center_points': 1, 'fraction_p': 1},
        headers=headers,
    )
    assert doe.status_code == 200

    csv_content = (
        'run_order,Dissolution,CU_RSD\n'
        '1,82,4.5\n'
        '2,85,4.2\n'
        '3,88,3.9\n'
        '4,90,3.8\n'
        '5,87,4.0\n'
    )
    files = {'file': ('results.csv', csv_content, 'text/csv')}
    imported = client.post(f'/studies/{study_id}/results/import', files=files, headers=headers)
    assert imported.status_code == 200
    assert imported.json()['imported_runs'] >= 4

    run_analysis = client.post(f'/studies/{study_id}/analysis/run', headers=headers)
    assert run_analysis.status_code == 200
    assert run_analysis.json()['status'] in ('done', 'failed')

    summary = client.get(f'/studies/{study_id}/analysis/summary', headers=headers)
    assert summary.status_code == 200

    ds = client.post(
        f'/studies/{study_id}/design-space/generate',
        json={'x_factor': 'A', 'y_factor': 'B', 'grid_size': 10, 'fixed_factors': {}},
        headers=headers,
    )
    assert ds.status_code == 200

    risk = client.post(
        f'/studies/{study_id}/risk/update',
        json={
            'initial_matrix': [
                {'process_step': 'Compression', 'cqa': 'CU', 'risk': 'high'},
                {'process_step': 'Milling', 'cqa': 'Dissolution', 'risk': 'medium'},
            ]
        },
        headers=headers,
    )
    assert risk.status_code == 200

    control = client.post(f'/studies/{study_id}/control-strategy/generate', headers=headers)
    assert control.status_code == 200

    reports = client.get(f'/reports?study_id={study_id}', headers=headers)
    assert reports.status_code == 200
    report_id = reports.json()[0]['id']

    submit = client.post(f'/reports/{report_id}/submit', headers=headers)
    assert submit.status_code == 200

    approve = client.post(f'/reports/{report_id}/approve', headers=headers)
    assert approve.status_code == 200

    exported = client.get(f'/reports/{report_id}/export.pdf', headers=headers)
    assert exported.status_code == 200
    assert exported.headers['content-type'].startswith('application/pdf')
