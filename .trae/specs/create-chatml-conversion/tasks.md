# Tasks

- [x] Task 1: 创建步骤2_1主脚本 `2_1_jsonl_to_chatml.py`
  - [x] SubTask 1.1: 定义Pydantic响应模型和LLM提示词
    - 任务描述生成响应模型：用于LLM生成随机角色扮演任务描述
    - Reasoning Content响应模型：用于LLM生成思考过程（Markdown格式）
    - 任务描述生成系统Prompt：要求LLM生成随机的角色扮演任务指令
    - Reasoning Content系统Prompt：要求LLM按照指定的思考顺序生成reasoning_content
  - [x] SubTask 1.2: 实现JSONL文件收集与随机抽样逻辑
    - 遍历输入目录中的书籍子目录，收集所有 `*_dialogue.jsonl` 文件
    - 实现 `--sample-count` 参数（默认10），支持随机抽样
    - 当 `sample_count=0` 时，处理所有文件，不进行抽样
  - [x] SubTask 1.3: 实现关联文件加载逻辑
    - 加载 `{stem}_characters.json`：提取 `characters`、`is_pov`、`pov_name`
    - 加载 `{stem}_facts.json`：提取 `summary` 用于前情提要
    - 加载 `world_settings.md`：世界观设定
    - 加载出场角色和POV角色对应的 `{角色本名}.md` 设定文件
    - 处理文件缺失的情况，跳过并记录警告
  - [x] SubTask 1.4: 实现用户角色确定逻辑
    - 第一人称视角：直接使用 `pov_name`
    - 第三人称视角：统计所有 `_characters.json` 中角色出场频率，选择最高的
    - 复用步骤1_4的 `filter_main_characters` 逻辑思路
  - [x] SubTask 1.5: 实现前情提要构建逻辑
    - 按段落顺序累加 `_facts.json` 中的 `summary` 字段
    - 超过700字符时调用LLM总结为不超过500字符
    - 复用步骤1_5的 `summarize_context` 逻辑
  - [x] SubTask 1.6: 实现ChatML消息转换逻辑
    - 构建system消息：包含任务描述（LLM生成）、世界观设定、角色设定、前情提要
    - 角色分配：根据speaker与用户角色的关系分配role（user/assistant）
    - 相邻消息合并：连续相同role的消息合并，收集所有speaker
    - 首条消息调整：如果system后第一条是assistant，改为user
  - [x] SubTask 1.7: 实现Reasoning Content补全逻辑
    - 为每条assistant消息调用LLM生成reasoning_content
    - Prompt包含当前消息前面所有message的content
    - 按照spec中定义的思考顺序（环境分析、局势分析、策略制定、角色视角思考）
    - 输出格式为Markdown，无固定模板
  - [x] SubTask 1.8: 实现main函数和CLI参数解析
    - 参数：`--input`、`--output`、`--sample-count`（默认10）
    - 遍历输入目录中的书籍子目录，依次处理
    - 输出到 `{output_dir}/{book_name}/` 子目录
    - 已处理的文件可跳过

- [x] Task 2: 在 `run.py` 中注册步骤2_1
  - 添加 `register_step` 调用，step_id="2_1"，module_name指向新脚本
  - 默认输入：`{config.processed_data_dir}/1_1_scene_segmentation`
  - 默认输出：`{config.processed_data_dir}/2_1_chatml_conversion`
  - 默认参数：`sample_count: 10`

- [x] Task 3: 更新 `README.md` 中步骤2.1文档
  - 在步骤1之后新增步骤2.1的完整文档
  - 包含功能描述、处理流程、输入输出格式、使用方法、可选参数说明

# Task Dependencies
- Task 2 depends on Task 1（需要脚本文件存在才能注册模块路径）
- Task 3 can be done in parallel with Task 2
