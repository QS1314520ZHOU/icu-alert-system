\# ICU Alert System — Claude Code Instructions



\## 项目概述



ICU 智能预警与临床协同系统。



技术栈：



\- 后端：Python、FastAPI、MongoDB、Redis

\- 前端：Vue 3、TypeScript、Vite

\- AI：LLM、RAG、FunASR/SenseVoice

\- 部署：Docker Compose



\## Token与文件读取规则



不要为了了解项目而扫描或读取整个仓库。



每次任务必须遵循：



1\. 先根据下面的文件索引定位入口。

2\. 只读取当前任务涉及的文件和直接依赖。

3\. 优先使用 `rg` 搜索类名、函数名和API路径。

4\. 不要递归读取整个 `backend/app` 或 `frontend/src`。

5\. 不要重复读取当前会话中已经读取过的文件。

6\. 默认最多读取8个源代码文件。

7\. 如果确实需要读取超过12个文件，先说明原因。

8\. 对大文件只读取相关区段，不要每次读取完整文件。

9\. 修改前先输出简短计划，不要先做全仓分析。

10\. 不要读取模型权重、音频、日志、构建产物和依赖目录。



禁止无目的执行：



```bash

find . -type f

tree -a

cat backend/app/\*\*/\*.py

cat frontend/src/\*\*/\*.vue



