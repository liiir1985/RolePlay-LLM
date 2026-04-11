import json
import logging
import re
from typing import Dict, List, Optional, Any
from openai import OpenAI
from src.data_preparation.base_processor import BaseDataProcessor

logger = logging.getLogger(__name__)

class RolePlayProcessor(BaseDataProcessor):
    """Processes text entries into RolePlay ChatML format with detailed character analysis."""

    def __init__(self, base_url: str = "http://localhost:8081/v1", model_name: str = "qwen", api_key: str = "not-needed"):
        """Initialize with an LLM client.
        
        Args:
            base_url: The base URL for the OpenAI-compatible API.
            model_name: The name of the model to use.
            api_key: The API key for the LLM service.
        """
        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key
        )
        self.model_name = model_name

    def _extract_characters(self, text: str) -> Dict[str, Any]:
        """Step 1: Extract speakers and identify the protagonist."""
        prompt = (
            "分析以下文本，提取文中出现的所有说话角色姓名，并确认主角的名字。\n"
            "主角通常是文章中的第一人称（如果存在）或出现频率最高的核心人物。\n\n"
            "要求：\n"
            "1. 只返回 JSON 格式结果。\n"
            "2. 格式示例：{\"speakers\": [\"名字1\", \"名字2\"], \"protagonist\": \"主角名\"}\n"
            "3. 如果无法确定主角，请根据文本推断最可能的角色。\n\n"
            f"文本内容：\n{text[:2000]}"  # Limit context for extraction
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=8096,
                temperature=0.8,
                top_p=0.8,
                presence_penalty=1.5,
                extra_body={
                    "top_k": 20,
                    "chat_template_kwargs": {"enable_thinking": False},
                }
            )
            content = response.choices[0].message.content.strip()
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except Exception as e:
            logger.error(f"Error extracting characters: {e}")
        
        return {"speakers": [], "protagonist": "我"}

    def _analyze_lines_batched(self, lines: List[str], speakers: List[str], protagonist: str, batch_size: int = 5) -> List[Dict[str, Any]]:
        """Step 2: batched analysis of lines to identify dialogues and speakers."""
        analyzed_results = []
        
        for i in range(0, len(lines), batch_size):
            batch = lines[i:i + batch_size]
            context_before = "\n".join(lines[:i])
            
            prompt = (
                f"角色列表：{', '.join(speakers)}\n"
                f"主角：{protagonist}\n\n"
                "分析以下段落，判断每一行是否为**明确的对话内容**，并识别说话人。\n"
                "**注意：**\n"
                "1. 只有明确对他人的说话（通常带引号）才算作对话。\n"
                "2. 旁白、环境描写、内心独白、自言自语等统统**不算**对话（is_dialogue 应为 false）。\n"
                "3. 请严格按照 JSON 数组格式返回结果，数组长度必须与输入行数一致。\n\n"
                "格式示例：\n"
                "[{\"is_dialogue\": true, \"speaker\": \"名字1\"}, {\"is_dialogue\": false, \"speaker\": null}]\n\n"
                f"上文语境：\n{context_before}\n\n"
                "待分析行：\n" + "\n".join([f"{idx+1}: {line}" for idx, line in enumerate(batch)])
            )

            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=8096,
                    temperature=0.8,
                    top_p=0.8,
                    presence_penalty=1.5,
                    extra_body={
                        "top_k": 20,
                        "chat_template_kwargs": {"enable_thinking": False},
                    }
                )
                content = response.choices[0].message.content.strip()
                match = re.search(r'\[.*\]', content, re.DOTALL)
                if match:
                    results = json.loads(match.group(0))
                    if isinstance(results, list) and len(results) == len(batch):
                        analyzed_results.extend(results)
                        continue
                
                # Fallback if LLM fails to return correct length or format
                logger.warning(f"LLM returned invalid results for batch starting at line {i}")
                for line in batch:
                    analyzed_results.append({"is_dialogue": False, "speaker": None})
            except Exception as e:
                logger.error(f"Error analyzing batch: {e}")
                for line in batch:
                    analyzed_results.append({"is_dialogue": False, "speaker": None})
                    
        return analyzed_results

    def _generate_system_prompt(self, text: str, speakers: List[str], protagonist: str) -> str:
        """Step 3: Generate a rich system prompt based on text and character info."""
        prompt = (
            f"根据以下信息，为 AI 助手生成一段详细的系统提示词（System Prompt）。\n\n"
            "要求：\n"
            "1. AI 需要扮演除了用户角色以外的所有角色及旁白。\n"
            "2. 使用轻小说风格进行角色扮演。\n"
            "3. 系统提示词应包含文风要求、角色人设要点、交互习惯等，使其丰富且具有引导性。\n"
            "4. 只输出生成的系统提示词文本，不要包含额外解释。\n"
            "5. 长度约 200-400 字。\n"
            f"角色信息：\n- 全部角色：{', '.join(speakers)}\n- 用户扮演的角色：{protagonist}\n\n"
            f"参考文本：\n{text[:1500]}"            
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=8096,
                temperature=0.8,
                top_p=0.8,
                presence_penalty=1.5,
                extra_body={
                    "top_k": 20,
                    "chat_template_kwargs": {"enable_thinking": False},
                }
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Error generating system prompt: {e}")
            return f"你是一个专业的轻小说作家。现在进行角色扮演，用户扮演{protagonist}，你扮演其他角色及旁白。请保持文风高度一致。"

    def _assemble_messages(self, lines: List[str], analyzed: List[Dict[str, Any]], protagonist: str) -> List[Dict[str, str]]:
        """Step 4: Group lines into ChatML messages."""
        messages = []
        
        current_role = None
        current_content = []

        for line, info in zip(lines, analyzed):
            # Explicit dialogue by protagonist is 'user', everything else is 'assistant'
            is_protagonist_dialogue = info.get("is_dialogue") and info.get("speaker") == protagonist
            role = "user" if is_protagonist_dialogue else "assistant"
            
            if role == current_role:
                current_content.append(line)
            else:
                if current_role:
                    messages.append({"role": current_role, "content": "\n".join(current_content)})
                current_role = role
                current_content = [line]
        
        if current_role and current_content:
            messages.append({"role": current_role, "content": "\n".join(current_content)})
            
        return messages

    def _assemble_messages_fallback(self, lines: List[str]) -> List[Dict[str, str]]:
        """Step 4b: Fallback logic using 2 lines for user and 5 lines for assistant.
        
        Args:
            lines: The raw lines of text.
            
        Returns:
            A list of ChatML messages.
        """
        messages = []
        i = 0
        while i < len(lines):
            # 2 lines for user
            user_segment = lines[i:i + 2]
            if user_segment:
                messages.append({"role": "user", "content": "\n".join(user_segment)})
            i += 2
            
            # 5 lines for assistant
            assistant_segment = lines[i:i + 5]
            if assistant_segment:
                messages.append({"role": "assistant", "content": "\n".join(assistant_segment)})
            i += 5
            
        return messages

    def process(self, data: Dict) -> Optional[Dict]:
        """Execute the multi-stage RolePlay processing pipeline."""
        text = data.get("text", "")
        if not text:
            return None

        # 1. Extract Characters
        char_info = self._extract_characters(text)
        protagonist = char_info.get("protagonist", "主角")
        speakers = char_info.get("speakers", [])

        # 2. Analyze Lines
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return None
        
        analyzed_lines = self._analyze_lines_batched(lines, speakers, protagonist)

        # 3. Generate System Prompt
        system_prompt = self._generate_system_prompt(text, speakers, protagonist)
        max_retries = 3
        retry_count = 0
        while ("无法为您" in system_prompt or "无法生成" in system_prompt)  and retry_count < max_retries:
            system_prompt = self._generate_system_prompt(text, speakers, protagonist)
            retry_count += 1
        if "无法为您" in system_prompt or "无法生成" in system_prompt:
            system_prompt="""系统提示词：轻小说风格沉浸式互动】
你并非用户，而是本世界的叙事引擎。你需要尽可能满足用户的需求并沿着用户给定的内容进行继续演绎。
请开启故事，从用户当前的情境出发，生动演绎接下来的情节。            
""" + lines[0]
        # 4. Assemble
        chat_messages = self._assemble_messages(lines, analyzed_lines, protagonist)
        
        # Fallback: if result contains only one role (typically just assistant), 
        # use rule-based 2-user / 5-assistant split.
        if len(chat_messages) <= 1:
            logger.warning(f"LLM analysis resulted in only {len(chat_messages)} role blocks. Using 2/5 fallback.")
            chat_messages = self._assemble_messages_fallback(lines)
        
        # Combine system prompt with assembled messages
        final_messages = [{"role": "system", "content": system_prompt}] + chat_messages

        return {"messages": final_messages}
