# OptiStacks Knowledge Atlas

这是凸分析、非线性规划与分布式优化的静态可视化知识站点。它直接使用仓库内当前的
knowledge-classification tree，因此目录和 statement 不需要在前端重复维护。

## 构建数据

在仓库根目录运行：

```bash
python scripts/build_knowledge_site.py
```

脚本会读取三套当前知识树并在 `site/data/` 生成网页数据，同时生成带统计信息的
`site/data/manifest.json`。源 JSON 不会被修改。

除正式知识分类树外，构建器还会收集当前主流程中能精确定位到目录节点的
structured intermediate statements，包括 topic-complete builder/reviewer 结果、
deferred ledger、v58 builder drafts、v60 reviewed intermediate records、v12
consolidated preview，以及 v10/v11 的全文 definition 结果。v11 中已经生成 JSON
但没有通过机械校验的候选也会保留；完全没有生成 statement payload 的失败 shard
无法展示。数学内容相同的多阶段副本只展示一次；未通过内容保留 pipeline stage、
deferred reason 和 review comment。同一目录节点内标题相同的记录也只保留一条，
正式记录优先。

## 本地打开

浏览器出于安全策略不能用 `file://` 直接读取 JSON，请启动一个静态服务器：

```bash
python -m http.server 8000 -d site
```

然后访问 <http://localhost:8000>。

站点功能包括：

- 凸分析 / 非线性规划 / 分布式优化三领域切换；
- 完整的递归目录浏览与章节跳转；
- 当前节点的直接父节点与直接子节点导航；
- statement 的正文、公式、假设、结论、前置节点、notation 与中间阶段信息展示；
- URL hash 深链接与移动端布局。

## 质量审阅

目录节点和 statement 卡片都提供独立的质量问题入口。目录问题可以标记拆分、
合并、命名和父子层级；statement 问题可以标记自然语言、数学正确性、假设、
公式渲染、放置和证据问题。记录保存在浏览器 `localStorage` 中，可以在
`Quality review` 队列中回到原条目、标记 resolved，并导出为
`optistacks-quality-review-YYYY-MM-DD.json`。导出包包含目标路径、内容快照、
问题类型、严重度和审阅意见，可作为后续修订流程的输入。

## 主题名称

高可见度章节和一级 topic 的名称直接记录在 `site/data/*.json` 中，不使用前端
显示别名。topic ID、父子层级、URL hash 和 statement 归属保持不变。
