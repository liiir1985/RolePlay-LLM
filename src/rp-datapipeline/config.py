import os
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class LLMConfig:
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-3.5-turbo"
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: int = 60
    max_retries: int = 3
    retry_delay: float = 1.0


@dataclass
class Config:
    llm: LLMConfig = field(default_factory=LLMConfig)
    
    raw_data_dir: str = "data/raw"
    processed_data_dir: str = "data/processed"
    final_data_dir: str = "data/final"
    
    def __post_init__(self):
        self.llm.api_key = os.getenv("OPENAI_API_KEY", self.llm.api_key)
        self.llm.base_url = os.getenv("OPENAI_BASE_URL", self.llm.base_url)
        self.llm.model = os.getenv("OPENAI_MODEL", self.llm.model)
        
        raw_data_dir_env = os.getenv("RAW_DATA_DIR")
        if raw_data_dir_env:
            self.raw_data_dir = raw_data_dir_env
        
        processed_data_dir_env = os.getenv("PROCESSED_DATA_DIR")
        if processed_data_dir_env:
            self.processed_data_dir = processed_data_dir_env
        
        final_data_dir_env = os.getenv("FINAL_DATA_DIR")
        if final_data_dir_env:
            self.final_data_dir = final_data_dir_env


_config: Optional[Config] = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config()
    return _config
