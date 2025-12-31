# Bank_Statement_converter

### 防线 1: 风险信号检测
- ✅ **4 类风险信号检测**
  - 低置信度检测 (P0/P1/P2 字段优先级)
  - 结构异常检测 (列数、行完整性、跨页)
  - 逻辑错误检测 (余额守恒、日期范围)
  - 银行模板识别 (RBC/TD/BMO/Scotiabank/CIBC)
### 防线 2: 增强逻辑检测
- ✅ **硬规则 (5 大规则)**
  - 日期范围验证 (未来日期、单调性)
  - 金额格式验证 (小数位、合理范围)
  - 逐行余额守恒 (±$0.02 容差)
  - 整体余额守恒
  - CR/DR 符号检查
- ✅ **错误模式库 (7 种默认模式)**
  - 括号负数误读 (123.45) → 123.45
  - 缺少 $ 符号
  - 逗号小数点混淆 (欧洲格式)
  - 日期歧义 (MM/DD vs DD/MM)
  - 字母 O/0 混淆
  - 字母 l/1 混淆
  - 负数存款检测
- ✅ **反馈闭环** - 人工修正自动更新模式库

### OCR 引擎
- ✅ **Document AI 客户端**
  - 异步文档处理
  - 表格提取与智能列映射
  - 置信度评分 (字段级 + 整体)
  - 开闭余额自动提取

### 核心管道
- ✅ **完整双层防线流程**
  1. Document AI 主引擎处理
  2. 风险信号检测
  3. 硬规则 + 错误模式检测
  4. 综合报告生成
- ✅ **异步处理支持**
- ✅ **批量文档处理**
- ✅ **详细日志记录**

### 数据模型
- ✅ **OCRResult** - OCR 结果、交易记录、风险信号
- ✅ **TransactionRow** - 单笔交易 (7+ 字段 + 置信度)
- ✅ **ValidationReport** - 验证报告 (规则违规 + 风险信号)
- ✅ **ErrorPattern** - 错误模式定义

### 报告生成
- ✅ **CSV 导出** - 交易数据 + 置信度分数
- ✅ **JSON 风险报告** - 完整验证元数据
- ✅ **文本摘要** - 人类可读的风险总结
- ✅ **建议生成** - 基于验证结果的操作建议
- ✅ **业务摘要** - 面向会计同事的结论摘要
- ✅ **复核行导出** - 需要人工确认的交易行

### 实验与测试界面
- ✅ **Web UI** - FastAPI + 静态前端用于上传与结果查看

---

## 📁 项目结构

```
bank_statement_converter/
├── core/                          # 核心处理引擎
│   ├── document_ai_client.py      # Document AI 客户端 
│   └── pipeline.py                # 主处理管道 
├── models/                        # 数据模型
│   ├── ocr_result.py              # OCR 结果模型 
│   └── validation_report.py      # 验证报告模型 
├── validators/                    # 双层防线验证器
│   ├── risk_signal_detector.py   # 防线1: 风险检测 
│   ├── hard_rules_validator.py   # 防线2: 硬规则 
│   └── error_pattern_db.py       # 防线2: 错误模式库 
├── utils/                         # 工具类
│   ├── parsing.py                # 通用解析 
│   └── report_generator.py       # 报告生成 
├── web/                           # Web UI
├── config/                        # 配置文件
│   └── error_patterns.json       # 错误模式持久化
├── README.md                      # 完整文档
└── requirements.txt               # 依赖管理
```

**总代码量**: ~2,200 行

---

## 🎯 核心特性

### 准确性保障
- **双层防线**: 风险检测 + 逻辑检查
- **7 种错误模式**: 常见 OCR 错误回归检测
- **数学约束**: 余额守恒 + 金额格式验证
- **目标准确率**: 90%+

### 可追溯性
- **详细风险报告**: 触发原因 + 位置 + 严重程度
- **规则违规详情**: 期望值 vs 实际值
- **错误模式匹配**: 已知错误特征识别

### 可扩展性
- **模块化设计**: 清晰的关注点分离
- **可配置**: ValidationConfig 灵活控制行为
- **持久化**: 错误模式 JSON 存储 + 自动更新
- **反馈闭环**: 人工修正 → 模式库更新

---

## 🚀 使用示例

```python
import asyncio
from bank_statement_converter.core import (
    BankStatementPipeline, 
    PipelineConfig,
    DocumentAIConfig
)

# 配置
config = PipelineConfig()
config.docai_config = DocumentAIConfig(
    project_id="your-gcp-project",
    location="us",
    processor_id="your-processor-id"
)

# 处理
pipeline = BankStatementPipeline(config)

async def main():
    result, report = await pipeline.process("statement.pdf")
    print(f"Status: {report.validation_status}")
    print(f"Confidence: {report.overall_confidence:.1%}")

asyncio.run(main())
```

**输出文件**:
- `output/xxx_<timestamp>.csv` - 交易数据
- `output/xxx_risk_report_<timestamp>.json` - 风险报告
- `output/xxx_business_summary_<timestamp>.json` - 业务摘要
- `output/xxx_review_rows_<timestamp>.csv` - 需复核交易行

---

## 📋 已实现的架构设计

### 处理流程
```
Document AI 处理
    ↓
风险信号检测
    ↓
硬规则 + 错误模式
    ↓
综合报告
