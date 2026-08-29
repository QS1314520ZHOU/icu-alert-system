# 病种中心 Mock 数据审计表

## 审计时间
2026-08-20

## 审计范围
- frontend/src/views/disease-center/*.vue
- backend/app/services/rule_core_client.py
- backend/app/config.py

## 整改状态

| 文件 | 问题 | 风险等级 | 整改状态 | 整改内容 |
|------|------|----------|----------|----------|
| DiseaseCenterAi.vue | generateMockReply() 返回假AI回答 | HIGH | ✅ 已完成 | 删除mock函数，添加错误处理 |
| DiseaseCenterAi.vue | alert() 弹窗提示 | MEDIUM | ✅ 已完成 | 替换为ElMessage组件 |
| DiseaseCenterAi.vue | 硬编码模型名称和置信度 | HIGH | ✅ 已完成 | 动态获取模型信息 |
| DiseaseCenterDiseases.vue | mockDiseases 硬编码病种列表 | HIGH | ✅ 已完成 | 删除mock，调用API |
| DiseaseCenterDiseases.vue | alert('编辑功能开发中') | MEDIUM | ✅ 已完成 | 替换为ElMessage组件 |
| DiseaseCenterDiseases.vue | fallback到mock数据 | HIGH | ✅ 已完成 | 删除fallback，显示错误状态 |
| DiseaseCenterOffline.vue | mockPackages 硬编码离线包 | HIGH | ✅ 已完成 | 删除mock，调用API |
| DiseaseCenterOffline.vue | alert()/confirm() 弹窗 | MEDIUM | ✅ 已完成 | 替换为ElMessage/ElMessageBox组件 |
| DiseaseCenterOffline.vue | fallback到mock数据 | HIGH | ✅ 已完成 | 删除fallback，显示错误状态 |
| DiseaseCenterPhenotypes.vue | mockDiseases/mockRules 硬编码数据 | HIGH | ✅ 已完成 | 删除mock，调用API |
| DiseaseCenterPhenotypes.vue | alert() 弹窗 | MEDIUM | ✅ 已完成 | 替换为ElMessage组件 |
| DiseaseCenterPhenotypes.vue | fallback到mock数据 | HIGH | ✅ 已完成 | 删除fallback，显示错误状态 |
| DiseaseCenterQuality.vue | mockIssues 硬编码质量问题 | HIGH | ✅ 已完成 | 删除mock，调用API |
| DiseaseCenterQuality.vue | alert() 弹窗 | MEDIUM | ✅ 已完成 | 替换为ElMessage组件 |
| DiseaseCenterQuality.vue | fallback到mock数据 | HIGH | ✅ 已完成 | 删除fallback，显示错误状态 |
| DiseaseCenterReviews.vue | mockReviews 硬编码审核项 | HIGH | ✅ 已完成 | 删除mock，调用API |
| DiseaseCenterReviews.vue | alert()/confirm() 弹窗 | MEDIUM | ✅ 已完成 | 替换为ElMessage/ElMessageBox组件 |
| DiseaseCenterReviews.vue | fallback到mock数据 | HIGH | ✅ 已完成 | 删除fallback，显示错误状态 |
| DiseaseCenterScores.vue | mockGroups 硬编码评分组 | HIGH | ✅ 已完成 | 删除mock，调用API |
| DiseaseCenterScores.vue | mockResult 硬编码评分结果 | HIGH | ✅ 已完成 | 删除mock，调用API |
| DiseaseCenterScores.vue | fallback到mock数据 | HIGH | ✅ 已完成 | 删除fallback，显示错误状态 |
| DiseaseCenterTerminology.vue | mockCategories/mockTerms 硬编码数据 | HIGH | ✅ 已完成 | 删除mock，调用API |
| DiseaseCenterTerminology.vue | fallback到mock数据 | HIGH | ✅ 已完成 | 删除fallback，显示错误状态 |
| rule_core_client.py | RuleCoreClient 依赖第二套服务 | HIGH | ✅ 已完成 | 删除文件，迁移到内部服务 |
| config.py | RULE_CORE_URL 配置 | HIGH | ✅ 已完成 | 删除配置项 |

## 整改总结

### 已完成
1. ✅ 删除所有mock数据和fallback逻辑
2. ✅ 替换alert()/confirm()为ElMessage/ElMessageBox组件
3. ✅ 删除RuleCoreClient依赖
4. ✅ 创建内部clinical_scoring_service.py
5. ✅ 更新disease_center.py使用内部服务
6. ✅ 添加错误状态显示

### 待实现
1. ⏳ 术语搜索功能
2. ⏳ 病种管理功能
3. ⏳ 表型规则功能
4. ⏳ 审核管理功能
5. ⏳ 离线包管理功能
6. ⏳ 质量监控功能
7. ⏳ AI咨询功能

## 风险等级说明
- **HIGH**: 可能导致临床误判或数据不一致
- **MEDIUM**: 影响用户体验或代码质量
- **LOW**: 代码风格或文档问题
