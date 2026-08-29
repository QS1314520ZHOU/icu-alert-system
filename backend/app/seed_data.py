"""示例数据初始化。"""

from __future__ import annotations

import logging
from datetime import datetime

from app.models.disease_center import DiseaseDefinition, DiseaseStatus

logger = logging.getLogger(__name__)


async def seed_diseases():
    """初始化示例病种数据。"""
    from app.services import disease_service

    # 检查是否已有数据
    existing = await disease_service.list_diseases()
    if existing:
        logger.info("数据库已有数据，跳过初始化")
        return

    logger.info("开始初始化示例病种数据...")

    sample_diseases = [
        DiseaseDefinition(
            name="脓毒症",
            english_name="Sepsis",
            code="SEPSIS",
            category_id="infection",
            description="脓毒症是机体对感染的反应失调导致的危及生命的器官功能障碍。",
            definition="Sepsis is life-threatening organ dysfunction caused by a dysregulated host response to infection.",
            diagnostic_criteria="SOFA评分较基线升高≥2分，且存在感染",
            icd10_codes=["A40", "A41"],
            icd11_codes=["1G40", "1G41"],
            status=DiseaseStatus.PUBLISHED,
            version="v2.0.0",
        ),
        DiseaseDefinition(
            name="急性呼吸窘迫综合征",
            english_name="Acute Respiratory Distress Syndrome",
            code="ARDS",
            category_id="respiratory",
            description="ARDS是一种急性弥漫性肺损伤，导致非心源性肺水肿和严重低氧血症。",
            diagnostic_criteria="急性起病，双肺浸润，PaO2/FiO2≤300mmHg，排除心衰",
            icd10_codes=["J80"],
            icd11_codes=["CA40"],
            status=DiseaseStatus.PUBLISHED,
            version="v2.0.0",
        ),
        DiseaseDefinition(
            name="急性肾损伤",
            english_name="Acute Kidney Injury",
            code="AKI",
            category_id="nephrology",
            description="AKI是肾功能在短时间内（数小时至数天）急剧下降的临床综合征。",
            diagnostic_criteria="48小时内血肌酐升高≥0.3mg/dL或较基线升高1.5倍，或尿量<0.5ml/kg/h持续6小时",
            icd10_codes=["N17"],
            icd11_codes=["GB60"],
            status=DiseaseStatus.PUBLISHED,
            version="v1.0.0",
        ),
        DiseaseDefinition(
            name="感染性休克",
            english_name="Septic Shock",
            code="SEPTIC_SHOCK",
            category_id="circulation",
            description="感染性休克是脓毒症的一个亚型，伴有循环、细胞和代谢异常。",
            definition="Septic shock is a subset of sepsis with circulatory, cellular, and metabolic dysfunction.",
            diagnostic_criteria="需要血管活性药物维持MAP≥65mmHg，且血乳酸>2mmol/L",
            icd10_codes=["R57.2"],
            icd11_codes=["1G41"],
            status=DiseaseStatus.PUBLISHED,
            version="v2.0.0",
        ),
        DiseaseDefinition(
            name="弥散性血管内凝血",
            english_name="Disseminated Intravascular Coagulation",
            code="DIC",
            category_id="coagulation",
            description="DIC是一种获得性凝血功能紊乱，特征为全身性凝血激活和微血管血栓形成。",
            icd10_codes=["D65"],
            icd11_codes=["3B20"],
            status=DiseaseStatus.DRAFT,
            version="v1.0.0",
        ),
        DiseaseDefinition(
            name="多器官功能障碍综合征",
            english_name="Multiple Organ Dysfunction Syndrome",
            code="MODS",
            category_id="infection",
            description="MODS是指急性疾病过程中同时或序贯发生两个或以上器官或系统的功能障碍。",
            icd10_codes=["R65.3"],
            icd11_codes=["1G40"],
            status=DiseaseStatus.DRAFT,
            version="v1.0.0",
        ),
        DiseaseDefinition(
            name="重症急性胰腺炎",
            english_name="Severe Acute Pancreatitis",
            code="SAP",
            category_id="digestive",
            description="重症急性胰腺炎是伴有持续性器官衰竭的急性胰腺炎。",
            icd10_codes=["K85.1"],
            icd11_codes=["DC31"],
            status=DiseaseStatus.PUBLISHED,
            version="v1.0.0",
        ),
        DiseaseDefinition(
            name="肺栓塞",
            english_name="Pulmonary Embolism",
            code="PE",
            category_id="respiratory",
            description="肺栓塞是肺动脉被血栓或其他物质阻塞的疾病。",
            icd10_codes=["I26"],
            icd11_codes=["BB00"],
            status=DiseaseStatus.PUBLISHED,
            version="v1.0.0",
        ),
    ]

    for disease in sample_diseases:
        try:
            await disease_service.create_disease(disease)
            logger.info(f"创建病种: {disease.name}")
        except Exception as e:
            logger.error(f"创建病种失败: {disease.name} - {e}")

    logger.info(f"示例病种数据初始化完成，共创建 {len(sample_diseases)} 个病种")
