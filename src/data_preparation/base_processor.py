from abc import ABC, abstractmethod
from typing import Dict, Optional

class BaseDataProcessor(ABC):
    """Abstract base class for data entry processors."""
    
    @abstractmethod
    def process(self, data: Dict) -> Optional[Dict]:
        """Process a single data entry.
        
        Args:
            data: A dictionary containing the raw entry data.
            
        Returns:
            A dictionary containing the processed data, or None if skipped.
        """
        pass
