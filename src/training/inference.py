from unsloth import FastLanguageModel
from transformers import TextStreamer
import torch

# ==========================================
# 1. 配置路径
# ==========================================
# 填入你最后保存的 Checkpoint 文件夹路径（包含 adapter_config.json 的那个文件夹）
lora_dir = "outputs-Qwen35-0.8B/checkpoint-2700" 
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

while True:
    user_input = input("🗣️ 输入文本: ")
    
    if user_input.lower() in ["quit", "exit"]:
        print("👋 退出推理。")
        break
    if not user_input.strip():
        continue

    # 把文本转为 Token 并推入显卡
    inputs = tokenizer(text=[user_input], return_tensors="pt").to("cuda")

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