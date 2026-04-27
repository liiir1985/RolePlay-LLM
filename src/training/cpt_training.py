from unsloth import FastLanguageModel
from unsloth import UnslothTrainer, UnslothTrainingArguments
from transformers.trainer_utils import get_last_checkpoint
#模型下载
from modelscope import snapshot_download
import os

OUTPUT_DIR = "./outputs-Qwen35-0.8B"   # 模型输出保存目录

# [关键开关] 你是否修改了学习率，并想丢弃旧的优化器状态，开启"第二阶段"？
# True  -> 把最新的 Checkpoint 当作新起点，用新学习率从第 0 步重新开始。
# False -> 如果有 Checkpoint，就原样恢复之前的进度、学习率和步数（应对意外断电/关闭终端）。
NEW_LR_PHASE_2 = False

last_checkpoint = get_last_checkpoint(OUTPUT_DIR) if os.path.isdir(OUTPUT_DIR) else None
if last_checkpoint is None:
    print("🟢 状态：未检测到断点。准备开启【全新训练】...")
    model_dir = snapshot_download('Qwen/Qwen3.5-0.8B', local_dir='models/Qwen3.5-0.8B')
    NEEDS_PEFT_INIT = True
    RESUME_ARG = False
else:
    if NEW_LR_PHASE_2:
        print(f"🟡 状态：开启【新阶段训练】。将加载 {last_checkpoint} 的权重，并应用新学习率...")
        model_dir = last_checkpoint
        NEEDS_PEFT_INIT = False # 已经是装好 LoRA 的模型了，千万别再装一次
        RESUME_ARG = False      # 不读取优化器状态
        
        # 建议：如果开启新阶段，最好换个输出文件夹，防止覆盖旧断点
        OUTPUT_DIR = OUTPUT_DIR + "-Phase2" 
    else:
        print(f"🔵 状态：开启【严格恢复训练】。将从 {last_checkpoint} 接续先前的进度和参数...")
        model_dir = snapshot_download('Qwen/Qwen3.5-0.8B', local_dir='models/Qwen3.5-0.8B')
        NEEDS_PEFT_INIT = True  # 像第一次那样初始化
        RESUME_ARG = last_checkpoint # 明确传入断点路径


import torch
from trl import SFTTrainer
from transformers import TrainingArguments
from datasets import load_dataset

# 1. 配置参数
max_seq_length = 2048 # 根据显存调整
dtype = None # 自动检测 (Float16/Bfloat16)
load_in_4bit = False # 使用4bit量化节省显存

print(model_dir)
# 2. 加载模型和分词器
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name = model_dir, # 或者你的本地路径
    max_seq_length = max_seq_length,
    dtype = dtype,
    load_in_4bit = load_in_4bit,
    full_finetuning = False, # [NEW!] We have full finetuning now!
    local_files_only = True, # 强制只使用本地文件
)

# 仅在全新训练或严格恢复时，才需要套上 LoRA 外挂
if NEEDS_PEFT_INIT:
    # 3. 添加 LoRA 适配器 (持续预训练关键配置)
    model = FastLanguageModel.get_peft_model(
        model,
        r = 32, # LoRA Rank，持续预训练建议大一点 (32, 64, 128)
        target_modules = [
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        lora_alpha = 64,
        lora_dropout = 0,
        bias = "none",
        use_gradient_checkpointing = "unsloth", # True or "unsloth" for very long context
    )

from datasets import load_dataset

# 替换为 jsonl 文件所在目录
dataset_dir = "data/sft" 

# 加载目录下所有的 jsonl 文件
dataset = load_dataset("json", data_files={"train": f"{dataset_dir}/*.jsonl"}, split="train")

# 1. 数据已经是标准的消息格式，重写数据格式化函数
def format_sft(examples):
    all_messages = examples["messages"]
    formatted_texts = []
    
    for messages in all_messages:
        # 使用分词器自带的 chat_template 自动处理 <|im_start|> 和 <|im_end|> 等特殊 token
        # tokenize=False 意味着返回的是拼装好的字符串，而不是 token id 列表
        # add_generation_prompt=False 因为我们是在训练（包含完整回复），而不是在推理
        formatted_chat = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=False
        )
        formatted_texts.append(formatted_chat)
        
    return {"text": formatted_texts}

# 获取当前模型对应的正确的 EOS token
EOS_TOKEN = tokenizer.eos_token
print(EOS_TOKEN)

def append_eos(examples):
    texts = examples["text"]
    formatted_texts = []
    for text in texts:
        # 在每条文本末尾显式追加 EOS token
        formatted_texts.append(text + EOS_TOKEN)
    return {"text": formatted_texts}

#dataset = dataset.map(append_eos, batched=True)
dataset = dataset.shuffle(seed=42)
# dataset = dataset.select(range(50)) # 如果数据量很大可以切片测试
dataset = dataset.map(format_sft, batched=True)

# 打印一条数据看看列名，确保 dataset_text_field 填对了
print(f"数据列名: {dataset.column_names}")
print(dataset[10]['text'])

from transformers import TrainingArguments

trainer = UnslothTrainer(
    model = model,
    tokenizer = tokenizer,
    train_dataset = dataset,
    dataset_text_field = "text",
    max_seq_length = max_seq_length,
    dataset_num_proc = 4,
    #packing = True,

    args = UnslothTrainingArguments(
        per_device_train_batch_size = 3,
        gradient_accumulation_steps = 4,

        # Use warmup_ratio and num_train_epochs for longer runs!
        #max_steps = 120,
        warmup_steps = 50,
        # warmup_ratio = 0.1,
        num_train_epochs = 2,
        save_strategy = "steps",     # 设置按步数保存
        save_steps = 100,            # 每 100 步保存一次
        save_total_limit = 3,        # 最多保存 3 份，旧的会被自动删除

        # Select a 2 to 10x smaller learning rate for the embedding matrices!
        learning_rate = 2e-4,
        embedding_learning_rate = 5e-5,

        max_grad_norm = 1.0,
        disable_tqdm = False,

        logging_steps = 10,
        optim = "adamw_8bit",
        weight_decay = 0.001,
        lr_scheduler_type = "linear",
        seed = 3407,
        output_dir = OUTPUT_DIR,
        #report_to = "wandb", # Use TrackIO/WandB etc
    ),
)
from unsloth.chat_templates import train_on_responses_only
trainer = train_on_responses_only(
    trainer,
    instruction_part = "<|im_start|>user\n",
    response_part = "<|im_start|>assistant\n<think>",
)
trainer.train(resume_from_checkpoint = RESUME_ARG)