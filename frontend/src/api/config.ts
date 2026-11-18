// 运行时开关：是否使用内置 Mock 适配层（见 src/mocks/mockAdapter.ts）。
// - 默认：使用 Mock（前后端未联调前，独立演示结果页）。
// - VITE_USE_MOCK=false：走真实 /api 代理到后端 127.0.0.1:8000。
// 联调/部署时切换：在 frontend/.env 或 .env.production 中写入 VITE_USE_MOCK=false。

export const USE_MOCK: boolean = import.meta.env.VITE_USE_MOCK !== 'false'
