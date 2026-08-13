# 香港食安中心(CFS)营养数据对接记录

> 抓取日期:2026-08-01。链路已实测打通,编码为 UTF-8(非 Big5)。

## 端点与请求格式

### 1. 按名称搜索食物
```
POST https://www.cfs.gov.hk/tc_chi/nutrient/search3.php
Content-Type: application/x-www-form-urlencoded

keylang=C&inShortMode=0&fg_id=&fsg_id=&keyword=<关键词>&searchcriteria=and&keyword2=
```

**坑(重要)**:页面表单初始 action 是 `presearch3.php`,但 onsubmit 的 `strfun()`
会先把 action 改成 **`search3.php`** 再提交。直接 POST presearch3.php 只会拿到空表单页。

响应:候选列表,每个候选链接 `javascript:tosubmit('fg_id','fsg_id','food_id')`。

### 2. 获取食物营养详情
```
POST https://www.cfs.gov.hk/tc_chi/nutrient/fc-myreport.php
Content-Type: application/x-www-form-urlencoded

fg_id=<fg>&fsg_id=<fsg>&food_id=<food_id>&inShortMode=
```

响应:每 100 克可食部 × 18 项营养(能量、蛋白质、碳水、脂肪、膳食纤维、糖、
饱和脂肪、反式脂肪、胆固醇、钙、铜、铁、镁、锰、磷、钾、钠、锌、维C)+ 数据来源。

无需 cookie 即可访问;页面为 UTF-8。

## 数据来源(官方声明)

| 代号 | 来源 | 碳水口径 | 膳食纤维口径 |
|---|---|---|---|
| USDA | 美国农业部 FoodData Central | 总碳水 | 总膳食纤维 |
| CFC2002Ed2 | 中国疾控营养与食品安全所 | 总碳水 | **不溶性纤维** |
| FRL | 香港食安中心食物研究化验所 | 可利用碳水 | 总膳食纤维 |
| AFCD R2 (2022) | 澳洲新西兰食品标准管理局 | 可利用碳水 | 总膳食纤维 |
| Thai FCD 2025 | 泰国玛希隆大学 | 可利用碳水(除非标"总") | — |

- 能量口径:AFCD 为**不含膳食纤维**的能量,千焦按 1 kcal = 4.2 kJ 换算;USDA/CFC 为总能量。
- "NA"=无资料,"ND"=未检出,"Trace"=微量。
- 数值均为**每 100 克可食用部分**。

## 工具内落地

- `cfs_fetch.py`:search_food() / fetch_nutrient() / to_profile_row() 核心封装
- `batch_fetch_cfs.py`:批量抓取 5月+6月 SOP 唯一食材(395 个)→ ingredient_nutrients.csv
  - 名称清洗:品牌词、包装描述词(蓋/罐裝/盒裝)、加工形态(切絲/切粒)、数量尾巴
  - 匹配优先级:精确 → 候选名以关键词开头 → 候选名是关键词子词 → 相似度
  - 单字关键词(如"鹽")跳过前缀匹配,避免 鹽→鹽水鴨
  - fallback:主词无结果时用缩短词重试(雜豆粒→雜豆→豆)
  - 清水/水:无营养,直接零值行
  - 断点续跑:cfs_progress.json,每 25 个写盘
- 输出:`ingredient_nutrients.csv`(工具 NUTRIENT_FIELDS 9 项 + 胆固醇/钙/钾)
- 未匹配:`cfs_unmatched.json`(需人工确认,多为调味料/半成品:雞粉、雞球、雜豆等)

## 抓取结果(2026-08-01 实测)

- SOP 唯一食材:395 个(5月+6月合并)
- **营养库建成:267 个(68%)**,数据源分布:AFCD 96 / CFC 78 / FRL 68 / USDA 13 / ThaiFCD 8 / 水 4
- 未匹配 128 个:蔬菜/其他 58、半成品 33、调味料/酱汁 32、主食 5
  → 人工清单:`待人工处理食材清单.csv`
- 已修复的错误匹配:生粉→玉米澱粉、麻油→芝麻油、濃縮橙汁→鮮榨橙汁、水餃→菜肉水餃
- 无法匹配已剔除:香菇精粉、香菇貢丸、野菜鮮魚餅(CFS 无对应物)

## 与历史结果比对(compare_history.py)

- 历史结果 5/6月 共 323 条 → 匹配到 SOP 139 条
- **44 道菜全部食材匹配可计算**;21 道与历史差异 >30%
- 差异原因:① 历史结果含大量复用值(4月 96%、5月 75%、6月 49% 重复);② 口径不同:
  本工具按 SOP 生重直算(不虚构保留率),历史可能按熟重/保留率折算。
- 结论:历史结果仅作对照台账,不可作权威答案;工具输出为可审计的确定性计算。

## 官方方法对照(2026-08-01 核实 NLC 用户指南 + 技术指引)

来源:
- NLC 使用指南:https://www.cfs.gov.hk/english/programme/programme_nifl/nlc-user_guide.html
- 技术指引(间接营养分析法定义):https://www.cfs.gov.hk/english/food_leg/files/nl_technical_guidance_e.pdf
- 方法指引(能量公式/AOAC 检测):https://www.cfs.gov.hk/english/food_leg/files/nl_method_guidance_e.pdf
  (已下载到项目目录:nl_technical_guidance.pdf / nl_method_guidance.pdf)

### 官方"间接营养分析法"7 步 vs 本工具实现

| 官方步骤(技术指引 §47) | 本工具对应 |
|---|---|
| Step 2 从权威成分库取食材营养值 | CFS 营养搜寻器抓取(每100g可食部) |
| Step 3 修正可食部重量 | `edible_fraction`(默认1) |
| Step 4a 熟食数据→用 yield factor 调整生重→熟重 | `yield_factor`(默认1) |
| Step 4b 生食数据→retention factor 调整营养 + yield factor 调整重量 | `retention_factor` + `yield_factor` |
| Step 5 求和 = 食谱营养值 | `calculate_recipe()` 逐项求和 |
| Step 7 每100g / 每份 | `nutrients_per_100g` / `nutrients_per_serving` |

### 官方口径确认

- "1+7" 强制项 = 能量+蛋白质+总脂肪+饱和脂肪+反式脂肪+碳水+糖+钠(与工具字段一致)
- 碳水默认口径 = **可利用碳水**(Available;法定定义:总碳水−膳食纤维)
- 能量公式 = 4×可利用碳水 + 4×蛋白质 + 9×总脂肪 + 7×乙醇 + 3×有机酸
  → 工具的 4-9-4 校验(蛋白质×4+总脂肪×9+可利用碳水×4)完全符合(学生餐无酒精)
- 官方认可的调整因子数据源:
  - **USDA Table of Nutrient Retention Factors**(营养保留因子表)
  - **Food Yields Summarized by Different Stages of Preparations, USDA**(产出因子表)
  - 其余:McCance&Widdowson UK、FSANZ 澳洲、ASEAN、中国食物成分表 2002/2004
- NLC 计算数值保留 3 位小数;缺失营养按 0

### 待办(需用户决策)

1. 是否引入 USDA 保留因子表 + 产出因子表,为食材填默认 `retention_factor` / `yield_factor`
   (官方认可、可追溯,不属"虚构";需按烹调方式映射:煮/蒸/炒/焗/炸)
2. 碳水口径:USDA/CFC 来源食材为"总碳水",按法定定义应换算 `可利用碳水 = 总碳水 − 膳食纤维`

## 已知缺口(CFS 无数据,需供应商标签/实验室或人工)

- 雞粉、雞球、肉片(通用)、雜豆粒(CFS 只有具体豆类)等
- 调味料类(DTL 编码)部分命中(蠔油/茄汁有),部分缺失
- 半成品(山東菜肉餃、魚柳、蝦棗等)需按成品/近似食材人工指定

## 计算口径衔接(与 README 一致)

- SOP 克重 = 安士 × 28.35(读缓存值)
- 可食重量 = 下单克重 × 可食率(CFS 数据本身为可食部,edible_fraction 默认 1,
  需按食材实际调整:带骨肉类、带壳类)
- 单项营养 = 可食重量 ÷ 100 × 每100g营养值 × 营养保留率(第一版不虚构保留率,默认 1)
- 4-9-4 宏量能量校验:蛋白质×4 + 总脂肪×9 + 可利用碳水×4
  - 注意:若食材来自 USDA/CFC(总碳水口径),需换算可利用碳水(总碳水 - 膳食纤维),
    否则 4-9-4 校验会系统性偏大。第一版以"碳水口径"字段标注,换算规则待营养师确认。
