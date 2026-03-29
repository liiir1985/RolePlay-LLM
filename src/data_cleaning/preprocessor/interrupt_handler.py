import signal
import json
import logging
from pathlib import Path
from typing import Callable, Any, Optional

logger = logging.getLogger(__name__)

class InterruptHandler:
    def __init__(self, checkpoint_path: Path):
        self.checkpoint_path = checkpoint_path
        self.interrupted = False
        self.save_callback: Optional[Callable] = None
        
        signal.signal(signal.SIGINT, self._handle_interrupt)
        signal.signal(signal.SIGTERM, self._handle_interrupt)

    def _handle_interrupt(self, signum, frame):
        logger.warning(f"Interrupt received (signal {signum}). Gracefully shutting down...")
        self.interrupted = True
        if self.save_callback:
            self.save_callback()

    def set_save_callback(self, callback: Callable):
        self.save_callback = callback

    def save_state(self, current_line: int, state_data: dict, processed_scenes: int):
        checkpoint = {
            "current_line": current_line,
            "processed_scenes": processed_scenes,
            "state_data": state_data
        }
        with open(self.checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(checkpoint, f, ensure_ascii=False, indent=4)
        logger.info(f"Checkpoint saved to {self.checkpoint_path}")

    def load_state(self) -> Optional[dict]:
        if not self.checkpoint_path.exists():
            return None
        try:
            with open(self.checkpoint_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading checkpoint: {e}")
            return None

    def clear_checkpoint(self):
        if self.checkpoint_path.exists():
            self.checkpoint_path.unlink()
