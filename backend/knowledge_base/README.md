# ICU 离线知识包

## 目录约定

- `manifest.json`：知识包清单与文档元数据
- `docs/*.json`：结构化离线文档
- 兼容旧格式：根目录下的 `*.json/*.md/*.txt` 仍可被加载

## 文档 JSON 结构

```json
{
  "doc_id": "ssc_2021",
  "title": "Surviving Sepsis Campaign 2021",
  "summary": "摘要",
  "sections": [
    {
      "id": "ssc2021_1h_bundle",
      "section_title": "1-hour bundle",
      "recommendation": "1h Bundle",
      "recommendation_grade": "core_bundle",
      "tags": ["sepsis", "shock"],
      "text": "本地离线知识正文"
    }
  ]
}
```

## manifest.json 关键字段

- `package_id` / `name` / `version`
- `owner` / `updated_at`
- `documents[]`
  - `doc_id`
  - `title`
  - `source`
  - `category`
  - `priority`：越高越优先
  - `tags`
  - `local_ref`
  - `filename`

## 说明

本知识包设计目标：

1. **完全离线**
2. **可审计**
3. **可按院内规范覆盖外部指南摘要**
4. **可用于 RAG 检索与本地证据弹窗**

建议后续将院内 SOP、药品说明书摘要、护理 Bundle、导管 Bundle、抗菌药管理规范都按此结构继续扩充。
