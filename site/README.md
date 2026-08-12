# ReasAtlas

这是覆盖优化知识目录 A02–A16 的静态可视化知识站点，并保留此前发布的
Distributed Optimization 兼容域及其原有深链接。
它直接使用当前知识目录与 statement layer，因此目录和 statement 不需要在前端重复维护。

## 构建数据

在仓库根目录运行：

```bash
python scripts/import_source_domains.py --source /root/workspace/lcy/optistacks
python scripts/build_lazy_shards.py
```

导入脚本会从原始材料读取完整 A02–A16 目录，并保留已有网页中的全部非 campaign
statement 与人工调整过的目录名称；随后合并 v58 正式 statement、topic-complete
已接受结果和具有 payload 的 deferred 结果。它还会读取主教材 campaign 与 25 本
补充教材 campaign：正式 publish overlay 优先，其次使用机械校验通过的 review shard，
再使用尚未 review 的 PASS build shard。
新目录候选的 statement 会挂到其现有父节点，并保留原始 placement 和 review 状态；
没有正文或无法对应当前 A02–A16 目录的记录不会被强行归类。
分片脚本随后把每个领域拆成轻量目录与按章节加载的 shard：首次访问只读取目录骨架，
进入章节时才下载正文，已经访问的章节由内存与浏览器缓存复用。

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

- A02–A16 十五个完整领域，以及旧版 Distributed Optimization 兼容域切换；
- 可滚动的领域导航与完整递归目录浏览；
- 当前节点的直接父节点与直接子节点导航；
- statement 的正文、公式、假设、结论、前置节点、notation 与中间阶段信息展示；
- URL hash 深链接与移动端布局。

## 质量审阅

目录节点和 statement 卡片都提供独立的质量问题入口。目录问题可以标记拆分、
合并、命名和父子层级；statement 问题可以标记自然语言、数学正确性、假设、
公式渲染、放置和证据问题。记录保存在浏览器 `localStorage` 中。用户可以在
`My submissions` 中查看当前设备上的全部、open 或 resolved 记录，回到原条目、
更新状态，并导出为
`reasatlas-quality-review-YYYY-MM-DD.json`。导出包包含目标路径、内容快照、
问题类型、严重度和审阅意见，可作为后续修订流程的输入。

## 主题名称

高可见度章节和一级 topic 的名称直接记录在 `site/data/*.json` 中，不使用前端
显示别名。topic ID、父子层级、URL hash 和 statement 归属保持不变。
