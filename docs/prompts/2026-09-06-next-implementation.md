# 下一对话实施Prompt：家电整机评论洞察

请继续实施`D:\CS_Projects\big_data_web`中的家电整机评论洞察项目。当前方案已经确认，不要重新选题、扩大范围或重新设计业务流程。

## 开始前必须阅读

按以下顺序完整阅读，并以这些文件作为当前唯一实施依据：

1. `D:\CS_Projects\big_data_web\.specify\memory\constitution.md`
2. `D:\CS_Projects\big_data_web\specs\001-merchant-review-insights\spec.md`
   - 重点阅读“已批准能力表”“数据范围”“明确排除”。
3. `D:\CS_Projects\big_data_web\specs\001-merchant-review-insights\technical-selection.md`
   - 重点阅读每项技术的本地运行位置、已经取得的测试证据和尚未完成状态。
4. `D:\CS_Projects\big_data_web\specs\001-merchant-review-insights\plan.md`
5. `D:\CS_Projects\big_data_web\specs\001-merchant-review-insights\tasks.md`
6. `D:\CS_Projects\big_data_web\specs\001-merchant-review-insights\data-model.md`
7. `D:\CS_Projects\big_data_web\specs\001-merchant-review-insights\contracts\openapi.yaml`
8. `D:\CS_Projects\big_data_web\specs\001-merchant-review-insights\quickstart.md`
9. `D:\CS_Projects\big_data_web\data\gold\scope-filter-20260906-v3\summary.json`
10. `D:\CS_Projects\big_data_web\ml\xpu\README.md`
11. `D:\CS_Projects\big_data_web\docs\runs\xpu-environment-2026-09-03.md`

随后执行一次`git status --short`，保留所有已有改动，不覆盖或回退用户工作。再阅读将要修改任务对应的现有代码，不要重复扫描无关目录。

## 固定业务目标

前端用户选择具体商品后，只实现以下业务链：

1. 自动归纳正面和负面主题；
2. 统计每个主题的评论数量、占比和时间趋势；
3. 点击主题查看对应评论原文、评分和日期；
4. 从明确建议和负面抱怨中整理产品改进需求。

不要增加预警、推荐系统、竞品分析、图数据库、评论有用性预测或其他功能。

## 固定数据范围

- 原始数据：2,128,605条Appliances评论。
- 正式完整处理范围：139个家电整机、13个整机种类、116,728条有效英文历史评论。
- 前端商品集合＝完整NLP商品集合＝正式Gold商品集合。
- 第一阶段不处理零件、配件、滤芯、替换件或耗材。
- 复用`scope-filter-20260906-v3`，不要重新选择商品或改变筛选条件。

## 固定技术方案

- 已完成：Silver清洗、fastText语言识别、VADER整体情感、正式商品范围。
- ABSA：`yangheng/deberta-v3-base-end2end-absa`，revision为`23e6d43431a5f96d8a7b7b9721d59bbda30cc63d`。
- ABSA保存属性、属性情感、置信度、位置和完整原句；不声称生成完整观点三元组。
- 明确建议：评论切句后，全部句子直接进入`cross-encoder/nli-MiniLM2-L6-H768`；`entailment > contradiction`即接受。
- 不使用关键词筛选建议，也不使用MiniLM作为NLI前置召回。
- 聚类：`all-MiniLM-L6-v2`＋Fast Community Detection，参数固定为相似度`0.75`、最小社区`10`条不同评论。
- 自动命名：高频属性＋聚类中心观点短语＋模板规范化；无法可靠规范化时使用中心短语。
- 不训练或微调模型，不比较候选模型，不建立科研式基线或人工标注评价集。
- 只做工程验收：设备兼容、输出结构、输入输出对账、原文追溯、失败记录、运行时间和断点恢复。

## 本地运行方式

- Docker Spark：全量Silver处理以及后续join、groupBy、数量、占比、趋势和Gold聚合。
- Windows原生`ml/xpu/.venv`：ABSA、MiniLM和NLI推理；必须使用Intel Arc XPU，禁止静默回退CPU。
- Transformer不得在Spark partition或executor中加载。
- CPU普通Python：Fast Community Detection和轻量主题命名逻辑。
- MongoDB、FastAPI、Vue/ECharts：只读取验证通过的Gold并展示，不在API请求中运行Spark或模型。
- 旧TF-IDF主题和旧`demands-20260905T203953`不得发布为新版Gold。

## 实施顺序

严格按照`tasks.md`继续，第一项是T006：

1. T006：导出116,728条正式评论，实现句子切分和长文本按句界分块，并完成数量对账。
2. T007：实现Windows XPU ABSA分片推理、状态记录和断点续跑；先根据已有兼容检查完成程序，再执行正式范围。
3. T008：只检查已确定NLI模型的XPU兼容和吞吐，不比较其他模型。
4. T009：对全部评论句子执行NLI，生成明确建议。
5. T010：使用MiniLM与Fast Community Detection合并主题，并按批准方式自动命名。
6. T011：使用Spark生成数量、占比、月度趋势和主题—评论映射Gold。
7. T012：验证后将唯一新版Gold发布到MongoDB。
8. T013：实现FastAPI只读接口。
9. T014：实现Vue/ECharts完整业务流程并进行端到端验证。

不要跳过前置依赖，也不要重新运行已经完成且可以复用的全量清洗、语言识别和VADER。

## 工作与汇报规则

- 每个模块先按现有SDD实施，不重新讨论已确认方案。
- 新增或修改行为时先写针对性测试，再做最小实现；不要反复运行相同检查。
- 固定模型的短吞吐检查属于工程检查，可以进行；禁止为了挑选模型而运行多种方法或样本竞赛。
- 正式长任务开始前必须给出输入总数和基于固定基准的预计耗时。
- 正式运行时不要频繁轮询或向用户输出实时日志；使用程序自身的低频进度和最终结果。
- 每完成一个模块，只向用户简单汇报：完成内容、输入/输出数量、运行时间、验证结果、产生的文件、下一模块。
- 简单汇报后自动继续下一模块，不等待重复的“继续”，除非出现需要改变业务范围、技术选型或数据口径的真实阻塞。
- 不生成用户未要求的文字报告，不把运行日志包装成报告。
- 控制命令输出和上下文读取，避免过度检查和无意义token消耗。
- 未实际运行通过的内容不得写成完成；任何最终完成声明必须有最新验证证据。

现在从读取上述文件和执行T006开始，持续完成后续任务。
