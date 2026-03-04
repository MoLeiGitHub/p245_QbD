# QbD Beta 应用

基于 `FastAPI + PostgreSQL + Streamlit` 的 QbD Beta 原型，支持：

- 项目与 Study 管理
- DOE 设计（全因子/分数因子/2组分混料）
- CSV 结果导入与阈值标记
- ANOVA 与显著性分析
- Design Space 叠加可行域
- 风险更新与控制策略生成
- 报告审核流与 PDF 导出
- 4 角色 RBAC 与审计日志

## 目录

- `backend/app`: API 与业务逻辑
- `frontend/app.py`: Streamlit 前端
- `backend/tests`: 自动化测试
- `docker-compose.yml`: 一键启动
- `docs/小白操作指南.md`: 非技术用户操作说明

## 默认账号

- Owner: `owner@example.com / owner123`
- Editor: `editor@example.com / editor123`
- Reviewer: `reviewer@example.com / reviewer123`
- Viewer: `viewer@example.com / viewer123`

## 本地启动（不使用 Docker）

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# API
uvicorn backend.app.main:app --reload --port 18101

# Frontend（新终端）
API_BASE_URL=http://localhost:18101 streamlit run frontend/app.py
```

## Docker 启动

```bash
docker compose up --build
```

- API: `http://localhost:18101`
- Frontend: `http://localhost:18102`

## 关键 API

- `POST /auth/login`
- `POST /projects`
- `POST /projects/{id}/members`
- `POST /studies`
- `POST /studies/{id}/doe/generate`
- `POST /studies/{id}/results/import`
- `POST /studies/{id}/analysis/run`
- `GET /studies/{id}/analysis/summary`
- `POST /studies/{id}/design-space/generate`
- `POST /studies/{id}/risk/update`
- `POST /studies/{id}/control-strategy/generate`
- `POST /reports/{id}/submit`
- `POST /reports/{id}/approve`
- `POST /reports/{id}/reject`
- `GET /reports/{id}/export.pdf`
- `GET /audit-logs?project_id=...`

## 测试

```bash
cd backend
PYTHONPATH=. pytest -q
```
