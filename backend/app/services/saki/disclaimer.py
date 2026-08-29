"""S-AKI 免责声明与标准文本。"""
from __future__ import annotations

DISCLAIMER: str = "仅用于科研分析与临床决策支持，不替代医生诊断和治疗决策。"

PHENOTYPE_DISCLAIMER: str = (
    "电子表型计算结果基于规则引擎自动生成，需经临床医师人工复核后方可用于科研分析。"
)

EXPORT_DISCLAIMER: str = "导出数据已脱敏处理，仅限科研用途。"

ANALYSIS_DISCLAIMER: str = (
    "统计分析结果基于观察性数据，仅提示关联性，不可作为因果推断依据。"
)

LLM_DISCLAIMER: str = (
    "系统不使用大语言模型（LLM）作为疾病诊断金标准，所有表型判定均基于循证规则引擎。"
)
