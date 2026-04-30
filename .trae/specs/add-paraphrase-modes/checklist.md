# Checklist

## 命令行参数
- [x] `--mode` 参数已添加，支持 `normal`、`paraphrase`、`strict-paraphrase` 三种选项
- [x] `--mode` 参数的默认值为 `normal`
- [x] `--min-chars` 参数已添加，类型为int
- [x] `--min-chars` 参数的默认值为500

## 消息收集逻辑（必须以assistant结尾）
- [x] 消息收集功能：能够从指定位置开始向后遍历，累加content的字符数
- [x] 当累加字符数达到 `min_chars` 时，检查最后一条消息的role
- [x] 如果最后一条消息是assistant，则停止收集
- [x] 如果最后一条消息是user，则继续向后遍历，直到找到下一条assistant消息为止
- [x] 如果遍历完所有消息仍未找到assistant，则使用已收集的消息，但记录警告
- [x] 函数返回收集到的消息列表和下一个起始位置

## 引号去除功能
- [x] 能够去除英文双引号 `"..."`
- [x] 能够去除中文双引号 `"..."`
- [x] 能够去除直角引号 `「...」` 和 `『...』`
- [x] 只去除最外层的引号，保留内容中的其他字符

## Task Description System Prompt更新
- [x] 分析了现有 `TASK_DESCRIPTION_SYSTEM_PROMPT` 的结构
- [x] 更新了提示词，使其能够根据模式生成不同的任务描述
- [x] 对于转述模式，添加了以下要求：
  - AI需要生成足够长度的文本内容
  - 用户提供的对话内容需要自然地融入到生成的文本中
- [x] 对于严格转述模式，除了转述模式的要求外，还添加了：
  - 用户角色的发言严格限定在用户提供的内容范围内
  - AI不能为用户角色生成用户没有说过的对话
- [x] 普通模式保持现有行为不变

## Reasoning Content提示词检查
- [x] 仔细分析了现有 `REASONING_CONTENT_SYSTEM_PROMPT` 的内容
- [x] 评估了其是否适用于转述模式和严格转述模式
- [x] 如果需要调整，进行了相应的变更；如果不需要，记录了评估结果

## 转述模式核心逻辑
- [x] 实现了 `convert_to_paraphrase_mode` 函数
- [x] 实现了多轮处理逻辑：循环调用 `collect_messages_batch` 函数，直到所有消息处理完毕
- [x] 对于每一轮收集到的消息：
  - 从收集到的消息中筛选出所有role为user的消息
  - 只选取头1-2条user消息的content（优先选取前2条，如果只有1条则取1条）
  - 使用 `remove_quotes` 函数去掉这些content中的引号，用换行符拼接，作为最终的一条user消息
  - 将收集到的所有消息的完整content按顺序拼接，作为最终的一条assistant消息
- [x] 最终的消息结构为 [system, user, assistant, user, assistant, ...]（可能有多轮）
- [x] 不调用 `adjust_first_message_role` 函数

## 严格转述模式核心逻辑
- [x] 实现了 `convert_to_strict_paraphrase_mode` 函数
- [x] 实现了多轮处理逻辑：循环调用 `collect_messages_batch` 函数，直到所有消息处理完毕
- [x] 对于每一轮收集到的消息：
  - 从收集到的消息中筛选出所有role为user的消息
  - 使用 `remove_quotes` 函数去掉所有这些content中的引号，用换行符拼接，作为最终的一条user消息
  - 将收集到的所有消息的完整content按顺序拼接，作为最终的一条assistant消息
- [x] 最终的消息结构为 [system, user, assistant, user, assistant, ...]（可能有多轮）
- [x] 不调用 `adjust_first_message_role` 函数

## 集成
- [x] 新模式已集成到主处理流程中
- [x] 根据 `mode` 参数正确选择不同的转换逻辑
- [x] 当 `mode` 为 `normal` 时，使用现有的转换逻辑（包括调用 `adjust_first_message_role`）
- [x] 当 `mode` 为 `paraphrase` 时，使用转述模式的转换逻辑（不调用 `adjust_first_message_role`）
- [x] 当 `mode` 为 `strict-paraphrase` 时，使用严格转述模式的转换逻辑（不调用 `adjust_first_message_role`）
- [x] reasoning_content的生成逻辑在新模式下正常工作（如果适用）
- [x] `generate_task_description` 函数能够根据模式生成不同的任务描述

## 文档
- [x] README.md中已添加新模式的说明
- [x] README.md中已说明 `--mode` 参数的用法和三种模式的区别
- [x] README.md中已说明 `--min-chars` 参数的用法
- [x] README.md中已说明消息收集时必须以assistant结尾的规则
- [x] README.md中已说明转述模式和严格转述模式的System消息构建差异
- [x] README.md中已说明首条消息角色调整规则在不同模式下的差异
- [x] README.md中已说明多轮对话的处理方式
- [x] README.md中已添加使用示例
