# 营养素计算工具（香港学生餐）

## 项目结构
- `docs/` `data/` `scripts/` — 按类别分文件夹
- `nutrition_tool/` — Python 3.11 核心包（高内聚低耦合）
- `菜单+SOP/` — 输入 SOP Excel
- `tests/` — 测试

## 核心规则
1. 输入：SOP Excel（A–E 餐）→ 输出：TT 菜单系统格式 Excel（23 字段，含香港 8 项营养）
2. 营养数据库：香港食安中心 cfs.gov.hk + USDA retention/yield 因子（见技能 `hk-cfs-nutrient-fetch` / `food-nutrition-data`）
3. 未来：打包 exe/app 给营养师使用；集成 Flask 菜单系统 http://47.238.128.121:5000（测试账号 PATRICK/123456）
4. 版本化契约：接口变更需同步版本
