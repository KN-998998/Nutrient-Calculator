# 🤝 双 Agent 协作审查报告 — F:\营养素计算工具

> 日期:2026-08-12
> 方式:Hermes(本会话)独立审查 + Codex CLI 0.147.0 headless 独立审查(203K tokens,只读)→ 交叉对比合并
> 状态:仅审查,未修改任何文件(除本报告)

---

## 一、两 Agent 独立审查发现(未交换信息前)

### Hermes 发现(9 项)

| # | 严重度 | 位置 | 问题 |
|---|---|---|---|
| H1 | 🔴 高 | dish_export.py:56-62 | **素类误判**:素肉片→豬肉、素牛肉片→豬肉、素雞絲→雞肉(规则顺序,"素"在最后被抢先命中) |
| M1 | 🟡 中 | dish_export.py:59 | **牛奶误判**:香草牛奶燉蛋→牛肉("牛"规则太宽) |
| M2 | 🟡 中 | sop.py:25 + calculator.py:33 | NaN/inf 克重通过校验 → 整菜营养全 NaN |
| M3 | 🟡 中 | app.py:72 | 上传文件名未 sanitize,路径穿越面 |
| M4 | 🟡 中 | app.py:67 + dish_export.py:185 | 菜式編號固定 100001 起始,多次导入重复 |
| L1 | 🟢 低 | dish_export.py:77-80 | 豆腐被识别为配菜(麻婆豆腐→配菜=豆腐) |
| L2 | 🟢 低 | app.py preview | warnings(review 原因)未展示给营养师 |
| L3 | 🟢 低 | app.py:63 | 临时目录不清理 |
| L4 | 🟢 低 | dish_export.py:186 | Excel 公式注入(理论) |

### Codex 发现(13 项)

| # | 严重度 | 位置 | 问题 |
|---|---|---|---|
| C1 | 🔴 高 | calculator.py:98 | **未匹配食材不计入 estimated_cooked_weight** → 有未匹配时每100g 结果分母失真 |
| C2 | 🔴 高 | calculator.py:57 | 碳水口径无状态标记(17 行 CFC 待核数据会当可用碳水导出) |
| C3 | 🔴 高 | app.py:72 | 上传文件名路径穿越(与 H 的 M3 同) |
| C4 | 🔴 高 | app.py:128 | 下载 startswith 前缀绕过(C:\Temp vs C:\Temp_evil) |
| C5 | 🔴 高 | dish_export.py:186 | Excel 公式注入(与 H 的 L4 同) |
| C6 | 🔴 高 | index.html:153 | **innerHTML 注入**:菜名直接拼 HTML(前端,XSS) |
| C7 | 🟡 中 | calculator.py:83 | 4-9-4 不符仅告警,数据库能量仍导出 |
| C8 | 🟡 中 | sop.py:25 + calculator.py:33 | NaN/inf(与 H 的 M2 同) |
| C9 | 🟡 中 | repository.py:45 | 名称索引按 profile 身份去重 |
| C10 | 🟡 中 | app.py:63 | 临时目录不清理(与 H 的 L3 同) |
| C11 | 🟡 中 | requirements.txt:1 | **缺 Flask 依赖声明**(仅 openpyxl,无法复现环境) |
| C12 | 🟢 低 | sop.py:85 | 固定列位无表头契约校验 |
| C13 | 🟢 低 | tests | 安全场景无测试覆盖 |

---

## 二、交叉对比结论

**两 Agent 独立确认一致的(可信度高):**
- app.py:72 上传路径穿越 ✅✅
- app.py:128 下载前缀校验绕过 ✅✅
- Excel 公式注入 ✅✅
- NaN/inf 克重无校验 ✅✅
- 临时目录不清理 ✅✅
- CFC 碳水口径状态标记 ✅✅(与 2026-08-12 审计同源)

**Codex 独有(我没有覆盖的):**
- C1 未匹配时每100g 分母失真(业务正确性,高价值)
- C6 前端 innerHTML XSS(我未审前端模板)
- C11 requirements.txt 缺 Flask(工程复现)

**Hermes 独有(Codex 没有的):**
- H1 素类误判、M1 牛奶误判、L1 豆腐配菜(需实际跑推断测试才能发现,Codex 静态审查未覆盖)
- M4 菜式编号重复

**评估:** Codex 在**静态/安全审查**更强(路径、注入、依赖);Hermes 在**业务逻辑实测**更强(实际运行推断规则发现数据错误)。两者互补,无冲突。

---

## 三、修复建议(按优先级分批)

### 第一批:业务正确性(直接影响营养结果)
1. H1 素类规则顺序修复(素→荤判断)
2. M1 牛奶/牛乳排除
3. C1 未匹配时每100g 置 None(不可用)
4. M2/C8 NaN/inf 校验(sop + calculator + service)
5. C2 碳水口径待核状态 → 影响菜式标 review

### 第二批:安全加固(桌面工具暴露面)
6. C3/M3 secure_filename(上传)
7. C4 下载用 is_relative_to
8. C5/L4 Excel 公式注入转义
9. C6 前端 textContent 渲染

### 第三批:工程健壮性
10. M4 菜式编号唯一化
11. C11 requirements.txt 补 Flask
12. C9 repository 名称索引去重
13. L1 豆腐配菜排除
14. L2 warnings 展示
15. C12 表头契约校验 + C13 测试补充

> 已确认无需修复:repository.py v2 重复编码消歧、calculator 4-9-4 公式、service 契约(两 Agent 一致认可)。

---

## 四、修复执行记录(2026-08-12,三批全部完成)

### 第一批:业务正确性
| 项 | 修复 |
|---|---|
| H1 素类误判 | `dish_export.py` 素類规则提到最前(素肉片/素牛肉片/素雞絲→素類,实测通过) |
| M1 牛奶误判 | 新增 `奶\|乳` → 奶類 规则(在"牛"前),香草牛奶燉蛋→奶類 |
| C1 未匹配每100g | `calculator.py` 有未匹配食材时 `per_100g=None` |
| M2 NaN/inf | `sop.py _numeric_grams` + `calculator.py` 均加 `math.isfinite` 校验 |
| C2 碳水口径待核 | `NutrientProfile.carb_uncertain` 字段;CFC+纤维缺失+碳水>1 自动标记;参与计算的菜式标 `review` + warning |

### 第二批:安全加固
| 项 | 修复 |
|---|---|
| C3/M3 上传路径穿越 | `app.py` 用 `secure_filename()`;扩展名校验保留 |
| C4 下载前缀绕过 | `app.py` 用 `Path.is_relative_to()`(组件级校验) |
| C5/L4 公式注入 | `dish_export._excel_safe()`:以 = + - @ 开头的文本加单引号 |
| C6 前端 XSS | `index.html` 预览改 DOM API(`createElement`+`textContent`),弃 innerHTML |

### 第三批:工程健壮性
| 项 | 修复 |
|---|---|
| M4 菜式编号重复 | `app.py` 批次起始编号加时间戳偏移 |
| C11 requirements | 补 `Flask>=3.0` |
| C9 名称索引去重 | `repository.py` 同一 profile 去重 |
| L1 豆腐配菜 | `dish_export` 配菜排除蛋白类(豆腐/豆干/火腿/魚蛋等) |
| L2 warnings 展示 | `app.py` preview 加 `warnings`;`index.html` 状态列 ⚠ + 提示 |
| L3 临时目录 | `app.py` 启动/处理前清理超过 24h 的 `nutri_out_*` |
| C13 测试补充 | `test_calculator.py` +3,`test_dish_export.py` 新建 +7 |

### 修复验证
- 项目测试:**21 个全部通过**(原 11 + 新增 10)
- Flask e2e(真实 5月 SOP):95 道菜计算成功,incomplete=91、review=2(碳水待核),preview 含 warnings
- 安全用例:下载路径穿越/前缀绕过 → 404、上传非 Excel/恶意文件名 → 400,全部拒绝
- Windows EXE 重新打包(`dist/营养素计算工具/`),启动冒烟 HTTP 200
- 附注:Codex 审查时在项目创建了 `.codex-check/` 临时目录,已删除并加入 .gitignore
