# 知识库语料（materials）

本目录存放 RAG 知识库的**首批语料**与入库清单，属于 F10「首批技术资料入库」的交付物。
语料与清单随 Git 维护，可追溯、可评审；内容版权归原作者/来源，入库前请确认可转载。

## 目录结构

```
materials/
├── manifest.json          # 入库清单（批量脚本唯一入口）
├── notes/                 # 本地文本/ Markdown 语料
└── (可按需新增) docs/ / urls/
```

## manifest.json 条目格式

每条必须且只能提供 `path` 或 `url` 之一；`source_type` 会根据二者自动推断
（path→text，url→url）。

```jsonc
{
  "items": [
    {
      "path": "notes/xxx.md",       // 相对 materials 目录的文件路径
      "title": "标题（可空，缺省用文件名/source）",
      "category": "ai",             // 技术类别，用于检索过滤
      "skill_tags": ["agent", "rag"],   // 可空
      "role_target": "ai_application_engineer", // 可空，供后续 Gap 检索
      "lang": "zh"
    },
    {
      "url": "https://docs.example.com/guide",
      "title": "某官方文档",
      "category": "ai"
    }
  ]
}
```

## 入库

```bash
.venv/bin/python -m scripts.ingest_materials --dry-run   # 预览将入库的条目
.venv/bin/python -m scripts.ingest_materials            # 正式入库
```

幂等：脚本可安全重跑，同 `source` 重复入库为替换式，不产生重复 chunk。

## 说明

- 当前清单仅含 1 条示例（项目简介），用于打通入库链路。请按同一格式补充
  2~50 份真实、可信的技术资料后重新入库。
- Embedding 若不可用（无 key / API 失败）会自动走确定性哈希向量兜底，入库与
  检索链路不中断。