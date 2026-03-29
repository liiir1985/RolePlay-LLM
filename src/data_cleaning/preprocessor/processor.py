import os
import json
import logging
import time
from pathlib import Path
from typing import List, Dict, Optional
from .models import (
    StorySceneFile, 
    DataBlock
)
from .state_manager import StateManager
from .llm_annotator import LLMAnnotator, BatchResponse
from .interrupt_handler import InterruptHandler

logger = logging.getLogger(__name__)

class StoryProcessor:
    def __init__(
        self, 
        input_dir: Path, 
        main_characters: List[str],
        batch_size: int = 200
    ):
        self.input_dir = input_dir
        self.story_file = input_dir / "story.txt"
        self.output_dir = input_dir / "structured"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.state_manager = StateManager(main_characters)
        self.llm = LLMAnnotator()
        self.interrupt_handler = InterruptHandler(input_dir / "resume_state.json")
        self.batch_size = batch_size
        
        self.current_line_idx = 0
        self.current_scene_idx = 1
        self.current_scene_data: List[DataBlock] = []
        self.scene_start_line = 0
        
        # Resume if checkpoint exists
        checkpoint = self.interrupt_handler.load_state()
        if checkpoint:
            logger.info(f"Resuming from line {checkpoint['current_line']}")
            self.current_line_idx = checkpoint['current_line']
            self.current_scene_idx = checkpoint.get('processed_scenes', 1)
            self.state_manager.load_checkpoint(checkpoint['state_data'])
            self.scene_start_line = self.current_line_idx

        self.interrupt_handler.set_save_callback(self._on_interrupt)

    def _on_interrupt(self):
        self.interrupt_handler.save_state(
            current_line=self.current_line_idx,
            state_data=self.state_manager.get_snapshot(),
            processed_scenes=self.current_scene_idx
        )

    def process_story(self):
        with open(self.story_file, "r", encoding="utf-8") as f:
            all_lines = f.readlines()

        total_lines = len(all_lines)
        logger.info(f"Starting processing {total_lines} lines...")

        while self.current_line_idx < total_lines and not self.interrupt_handler.interrupted:
            end_idx = min(self.current_line_idx + self.batch_size, total_lines)
            batch_lines = all_lines[self.current_line_idx:end_idx]
            
            logger.info(f"Processing batch: lines {self.current_line_idx} to {end_idx}")
            
            # Call LLM
            response = self.llm.process_batch(
                batch_lines, 
                list(self.state_manager.characters.keys()),
                self.state_manager.get_snapshot()
            )
            
            if response:
                # Update summary first so it becomes part of the scene snapshot
                self.state_manager.plot_summary = response.updated_plot_summary
                self._handle_llm_response(response, self.current_line_idx, end_idx)
            else:
                logger.error(f"Failed to process batch {self.current_line_idx}. Retrying in 5s...")
                time.sleep(5)
                continue

            self.current_line_idx = end_idx
            
            # Save checkpoint after each batch to avoid loss
            self._on_interrupt()

        # Save final scene if any
        if self.current_scene_data and not self.interrupt_handler.interrupted:
            self._save_current_scene(total_lines)
            self.interrupt_handler.clear_checkpoint()

    def _handle_llm_response(self, response: BatchResponse, start_ln: int, end_ln: int):
        batch_internal_line = start_ln
        
        for block in response.data_blocks:
            # Update known characters list if new names appear
            for name in [block.speaker, block.actor, block.character]:
                if name and "/" in name: # Handle potential combined names (though now forbidden)
                    names = name.split("/")
                elif name:
                    names = [name]
                else:
                    names = []
                
                for n in names:
                    if n and n not in self.state_manager.known_characters:
                        self.state_manager.known_characters.append(n)

            # Update state Manager
            if block.dataType == "status_update":
                self.state_manager.update_status(block)
            elif block.dataType == "relationship_update":
                self.state_manager.update_relationship(block)
            elif block.dataType == "item_update":
                self.state_manager.update_items(block)
            elif block.dataType == "scene_change":
                # Scene change detected
                if any(b.dataType not in ["scene_change", "status_update", "relationship_update", "item_update"] for b in self.current_scene_data):
                    # Use accurate internal line counter
                    self._save_current_scene(batch_internal_line)
                
                self.current_scene_idx += 1
                self.current_scene_data = [block]
                self.scene_start_line = batch_internal_line
                self.state_manager.current_scene = block.new_scene or "新场景"
                
                # Increment line count for this block
                batch_internal_line += block.line_count
                continue
            
            self.current_scene_data.append(block)
            batch_internal_line += block.line_count

    def _save_current_scene(self, current_line_end: int):
        if not self.current_scene_data:
            return

        snapshot = self.state_manager.get_snapshot()
        scene_file = StorySceneFile(
            start_line=self.scene_start_line,
            end_line=max(current_line_end, self.scene_start_line + 1),
            plot_summary=snapshot["plot_summary"],
            character_states=snapshot["character_states"],
            character_relationships=snapshot["character_relationships"],
            character_items=snapshot["character_items"],
            data_blocks=self.current_scene_data
        )
        
        output_path = self.output_dir / f"{self.current_scene_idx}.json"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(scene_file.model_dump_json(indent=4))
        
        logger.info(f"Saved scene {self.current_scene_idx} to {output_path}")
        self.current_scene_data = []
        self.scene_start_line = current_line_end
