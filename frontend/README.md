# 知径前端

`frontend/web` 是知径 AI 个性化学习平台的唯一前端应用，使用 Vue 3、Vite、TypeScript、Vue Router、Pinia、Axios、ECharts、Lucide、Markdown-it 和 KaTeX。

## 本地开发

在项目根目录执行：

```powershell
cd frontend/web
npm install
npm run dev
```

打开 `http://127.0.0.1:5173/`。

开发服务器会将 `/api` 和 `/diagnosis/api` 请求代理到 `http://127.0.0.1:8000`。如需修改地址，可设置：

```powershell
$env:VITE_API_BASE_URL = "http://127.0.0.1:8000"
```

## 构建

```powershell
cd frontend/web
npm run build
npm run preview
```

FastAPI 会优先托管 `frontend/web/dist`，因此生产检查前需要先执行 `npm run build`。

## 页面路由

- `/`：知径首页
- `/dashboard`：学习工作台
- `/diagnosis`：学情诊断概览
- `/diagnosis/basic`：基础信息
- `/diagnosis/assessment`：知识水平评估
- `/profile`：学习者画像
- `/learning-path`：个性化学习路径
- `/resources`：学习资源
- `/assessment`：测评反馈
- `/history`：学习历史
- `/profile/settings`：个人中心

旧的 `frontend/platform` 和 `frontend/diagnosis` 静态页面已移除，后续前端功能统一在 `frontend/web` 中维护。
