import json
from pathlib import Path
from typing import Dict, List, Optional
from .models import (
    CharacterStatus, 
    Relationship, 
    CharacterItem, 
    CharacterClothing,
    DataBlock
)

class StateManager:
    def __init__(self, main_characters: List[str]):
        self.characters: Dict[str, CharacterStatus] = {
            name: CharacterStatus() for name in main_characters
        }
        self.relationships: Dict[str, List[Relationship]] = {
            name: [] for name in main_characters
        }
        self.items: Dict[str, List[CharacterItem]] = {
            name: [] for name in main_characters
        }
        self.known_characters: List[str] = list(main_characters)
        self.plot_summary: str = ""
        self.current_scene: str = "序章"

    def update_status(self, block: DataBlock):
        if not block.character or not block.updates:
            return
        if block.character not in self.characters:
            self.characters[block.character] = CharacterStatus()
        
        char_status = self.characters[block.character]
        # updates is now a StatusUpdateFields model
        update_data = block.updates.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if value is None:
                continue
            if hasattr(char_status, key):
                setattr(char_status, key, value)
            elif key in ["outerwear", "top", "bottom", "socks", "shoes"]:
                setattr(char_status.clothing, key, value)

    def update_relationship(self, block: DataBlock):
        if not block.character or not block.target:
            return
        if block.character not in self.relationships:
            self.relationships[block.character] = []
        
        rels = self.relationships[block.character]
        target_rel = next((r for r in rels if r.target_character == block.target), None)
        
        if not target_rel:
            target_rel = Relationship(target_character=block.target)
            rels.append(target_rel)
        
        if block.opinion:
            target_rel.opinion = block.opinion
        if block.new_event:
            target_rel.events.append(block.new_event)

    def update_items(self, block: DataBlock):
        if not block.character or not block.item_name or not block.action:
            return
        if block.character not in self.items:
            self.items[block.character] = []
        
        items = self.items[block.character]
        target_item = next((i for i in items if i.name == block.item_name), None)
        
        if block.action == "add":
            if not target_item:
                items.append(CharacterItem(name=block.item_name, state=block.new_state or ""))
        elif block.action == "remove":
            if target_item:
                items.remove(target_item)
        elif block.action == "modify":
            if target_item:
                target_item.state = block.new_state or target_item.state
            else:
                items.append(CharacterItem(name=block.item_name, state=block.new_state or ""))

        return {
            "character_states": {name: status.model_dump() for name, status in self.characters.items()},
            "character_relationships": {name: [r.model_dump() for r in rels] for name, rels in self.relationships.items()},
            "character_items": {name: [i.model_dump() for i in items] for name, items in self.items.items()},
            "known_characters": self.known_characters,
            "plot_summary": self.plot_summary
        }

    def load_checkpoint(self, data: dict):
        # Implementation for resume functionality
        if "character_states" in data:
            self.characters = {k: CharacterStatus.model_validate(v) for k, v in data["character_states"].items()}
        if "character_relationships" in data:
            self.relationships = {k: [Relationship.model_validate(r) for r in v] for k, v in data["character_relationships"].items()}
        if "character_items" in data:
            self.items = {k: [CharacterItem.model_validate(i) for i in v] for k, v in data["character_items"].items()}
        self.known_characters = data.get("known_characters", self.known_characters)
        self.plot_summary = data.get("plot_summary", "")
        self.current_scene = data.get("current_scene", "序章")
