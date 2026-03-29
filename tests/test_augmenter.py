import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from src.data_cleaning.novel_augmenter import NovelAugmenter, NovelInfo
import pandas as pd
import unittest
from unittest.mock import MagicMock, patch

class TestNovelAugmenter(unittest.TestCase):
    def setUp(self):
        self.augmenter = NovelAugmenter(api_key="fake_key", model_name="fake_model")

    def test_tag_loading(self):
        df = pd.DataFrame({
            'name': ['Test1', 'Test2'],
            'tags': ['Tag1, Tag2', 'Tag2, Tag3']
        })
        self.augmenter.load_existing_tags(df)
        self.assertEqual(len(self.augmenter.existing_tags), 3)
        self.assertIn('Tag1', self.augmenter.existing_tags)

    @patch('google.genai.Client')
    def test_augment_novel_known(self, mock_client):
        # Mocking the response
        mock_response = MagicMock()
        mock_response.text = '{"genre": "Fantasy", "tags": ["Magic", "Adventure"], "summary": "A cool story.", "unknown": false}'
        
        # Setup mock client behavior
        instance = mock_client.return_value
        instance.models.generate_content.return_value = mock_response
        
        result = self.augmenter.augment_novel("Overlord")
        
        self.assertIsNotNone(result)
        self.assertEqual(result.genre, "Fantasy")
        self.assertFalse(result.unknown)
        self.assertIn("Magic", self.augmenter.existing_tags)

    @patch('google.genai.Client')
    def test_augment_novel_unknown(self, mock_client):
        mock_response = MagicMock()
        mock_response.text = '{"genre": null, "tags": [], "summary": null, "unknown": true}'
        
        instance = mock_client.return_value
        instance.models.generate_content.return_value = mock_response
        
        result = self.augmenter.augment_novel("NonExistentBook123")
        
        self.assertIsNotNone(result)
        self.assertTrue(result.unknown)

if __name__ == "__main__":
    unittest.main()
