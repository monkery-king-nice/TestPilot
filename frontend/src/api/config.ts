// 运行时开关：是否使用内置 Mock 适配层（见 src/mocks/mockAdapter.ts）。
// 开发模式默认使用 Mock。生产构建默认使用同源 /api，可显式设置 true 体验示例。
// - VITE_USE_MOCK=false：走真实 /api 代理到后端 127.0.0.1:8000。
// 联调/部署时切换：在 frontend/.env 或 .env.production 中写入 VITE_USE_MOCK=false。

export const USE_MOCK: boolean = import.meta.env.VITE_USE_MOCK === undefined
  ? import.meta.env.DEV
  : import.meta.env.VITE_USE_MOCK !== 'false'
