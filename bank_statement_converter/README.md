# Bank Statement OCR Converter

面向加拿大银行账单的 OCR -> 结构化交易数据与风险验证管道。
主引擎为 Google Document AI，专注单引擎解析与规则校验。

## 核心特性

- 双层防线验证：风险信号检测 → 硬规则与错误模式库
- 高可追溯：输出 CSV/JSON 报告与复核清单
- 模块化设计：易于扩展规则与输出格式

## 依赖与前置条件

- Python >= 3.8
- Google Cloud Document AI：
  - 项目与处理器（processor_id）
  - 服务账号密钥 JSON（保存在后端服务器）

## 快速开始

### 1) 安装依赖
```bash
pip install -r requirements.txt
```

### 2) 代码方式配置 Document AI
```python
import asyncio
from bank_statement_converter.core import (
    BankStatementPipeline,
    PipelineConfig,
    DocumentAIConfig,
)

config = PipelineConfig()
config.docai_config = DocumentAIConfig(
    project_id="your-project-id",
    location="us",
    processor_id="your-processor-id",
    credentials_path="/absolute/path/to/service-account-key.json",
)

pipeline = BankStatementPipeline(config)

async def main():
    result, report = await pipeline.process("statement.pdf")
    print(report.validation_status, report.overall_confidence)

asyncio.run(main())
```

### 3) Web UI（本地实验）
编辑 `web/app.py`，填写以下常量：
```python
DOC_AI_PROJECT_ID = "your-project-id"
DOC_AI_PROCESSOR_ID = "your-processor-id"
DOC_AI_LOCATION = "us"
DOC_AI_CREDENTIALS_PATH = "/absolute/path/to/service-account-key.json"
```

启动：
```bash
python -m bank_statement_converter.web.run
```
访问 `http://127.0.0.1:8000`。

## 配置说明

```python
from bank_statement_converter.validators import ValidationConfig

config = ValidationConfig()
config.confidence_threshold = 0.85
```

## 输出内容

- `output/xxx.csv`：交易数据
- `output/xxx_risk_report_*.json`：风险验证报告
- `output/xxx_business_summary_*.json`：业务摘要
- `output/xxx_review_rows.csv`：需人工复核的行

## 目录结构

```
bank_statement_converter/
├── core/         # 核心管道 + OCR 客户端
├── validators/   # 风险检测、硬规则与错误模式
├── models/       # OCR 结果与报告模型
├── utils/        # 报告生成等工具
├── web/          # FastAPI + 静态前端
├── config/       # 配置文件（错误模式库等）
└── tests/        # 测试
```

## 安全提示

- 服务账号 JSON 只应保存在后端/服务器，**不要**提交到代码仓库。
- 如需部署到第三方环境，请确保密钥文件安全存放并限制访问权限。

## License

MIT
