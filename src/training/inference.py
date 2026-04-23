from unsloth import FastLanguageModel
from transformers import TextStreamer
import torch

# ==========================================
# 1. 配置路径
# ==========================================
# 填入你最后保存的 Checkpoint 文件夹路径（包含 adapter_config.json 的那个文件夹）
lora_dir = "outputs-Qwen35-0.8B/checkpoint-100" 
#lora_dir = "models/Qwen3.5-0.8B"

print(f"🚀 正在加载模型：{lora_dir} ...")

# ==========================================
# 2. 加载模型与分词器
# ==========================================
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name = lora_dir, 
    max_seq_length = 4096,
    dtype = None,
    #load_in_4bit = True, # 强烈建议开 4bit，27B 模型能在 24G 显存内轻松推理
)

# 开启 Unsloth 专属的推理加速机制 (提速 2 倍且省显存)
FastLanguageModel.for_inference(model)

# ==========================================
# 3. 初始化流式输出器
# ==========================================
# skip_prompt=True: 终端不会重复打印你输入的问题
# skip_special_tokens=True: 隐藏 <|endoftext|> 等特殊符号
streamer = TextStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)

# ==========================================
# 4. 终端交互循环
# ==========================================
print("\n" + "="*50)
print("✅ 模型加载完毕！请输入前缀文本让模型续写。(输入 'quit' 退出)")
print("="*50 + "\n")
SYSTEM_PROMPT = "你是一个优秀的轻小说作家，擅长以生动的笔触描写场景、人物性格以及推动故事情节。"
USER_PROMPT = "请以轻小说的笔触展开一段叙述。"
while True:
    user_input = input("🗣️ 输入文本: ")
    
    if user_input.lower() in ["quit", "exit"]:
        print("👋 退出推理。")
        break
    if not user_input.strip():
        continue
    messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT + "\n" + user_input},
            #{"role": "assistant", "content": user_input} # 将你的长文本切片作为 assistant 的回复
        ]
        
        # 使用分词器自带的 chat_template 自动处理 <|im_start|> 和 <|im_end|> 等特殊 token
        # tokenize=False 意味着返回的是拼装好的字符串，而不是 token id 列表
        # add_generation_prompt=False 因为我们是在训练（包含完整回复），而不是在推理
    formatted_chat = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True
    )
    # 把文本转为 Token 并推入显卡
    inputs = tokenizer(text=[formatted_chat], return_tensors="pt").to("cuda")

    print("🤖 模型输出: ", end="")
    
    # 启动流式生成
    _ = model.generate(
        **inputs,
        streamer=streamer,         # 绑定流式输出器
        max_new_tokens=1024,        # 一次最多生成的字数
        use_cache=True,            # 必须开启缓存以保证推理速度
        temperature=0.7,           # 创造力 (0.1 最严谨，1.0 最天马行空)
        top_p=0.9,
    )
    print("\n") # 这一次生成结束后换行，准备迎接下一次输入