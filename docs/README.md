# 营养素计算工具

面向学生餐 SOP 的可审计营养计算核心。计算结果可独立导出，也可由后续 Flask 菜单系统直接调用。

## 计算口径

- SOP 克重：`安士 × 28.35`（现有工作簿已经生成克重列，本工具读取克重列）
- 可食重量：`下单克重 × 可食率`
- 单项营养：`可食重量 ÷ 100 × 每100g营养值 × 营养保留率`
- 套餐营养：所有食材贡献求和
- 估计熟重：`可食重量 × 熟重得率`
- 每100g成品：`套餐总营养 ÷ 成品熟重 × 100`
- 宏量能量校验：`蛋白质×4 + 总脂肪×9 + 可利用碳水×4`

营养数据库的所有营养指标均须填写为“每100克可食用部分”。计算过程保留未四舍五入值，仅在导出展示时舍入。

## 快速开始

```powershell
python -m pip install -r requirements.txt

# 检查工作簿可解析情况
python main.py inspect-sop "菜单+SOP\finnal-2026年6月Lunch 學生餐單Menusop.xlsx"

# 从 SOP 提取唯一食材，生成待补充的营养数据库模板
python main.py make-template `
  "菜单+SOP\finnal-2026年6月Lunch 學生餐單Menusop.xlsx" `
  "ingredient_nutrients.csv"

# 补齐模板中的每100g营养值后批量计算
python main.py calculate-sop `
  "菜单+SOP\finnal-2026年6月Lunch 學生餐單Menusop.xlsx" `
  "ingredient_nutrients.csv" `
  "nutrition_results.json"
```

仅计算指定工作表：

```powershell
python main.py calculate-sop sop.xlsx ingredient_nutrients.csv result.csv `
  --sheets "6月A餐配料sop,6月B餐配料sop"
```

## 营养数据库字段

- `ingredient_code`：优先匹配现有 SOP 编码
- `ingredient_name`、`aliases`：编码缺失时的标准名及别名匹配
- 九项营养值：每100克可食用部分
- `edible_fraction`：可食率，0–1
- `yield_factor`：熟重得率，可因吸水而大于1
- `retention_factor`：初版统一营养保留率，0–1
- `source`、`source_food_id`：香港食安中心、供应商标签或实验室的可追溯来源

## 输出状态

- `passed`：食材全部匹配且没有质量警告
- `review`：计算完成，但能量或营养组成需要复核
- `incomplete`：至少一项食材未匹配，结果不可发布

## 后续集成

网站后端可直接调用：

```python
from nutrition_tool import calculate_recipe
```

推荐将自动计算值保存到 `calculated_*` 字段，审核发布值保存到 `published_*` 字段，并记录 SOP、食材数据库及计算规则版本。
