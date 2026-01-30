"""Configuration manager"""

from pathlib import Path
import json

class Config:
    def __init__(self, config_path=None):
        if config_path is None:
            # Default to config/config.json relative to project root
            self.config_path = Path(__file__).parent.parent.parent / 'config' / 'config.json'
        else:
            self.config_path = Path(config_path)
        
        # Load config if exists, otherwise use defaults
        if self.config_path.exists():
            with open(self.config_path) as f:
                self.config = json.load(f)
        else:
            self.config = self._get_defaults()
    
    def _get_defaults(self):
        """Default configuration"""
        project_root = Path(__file__).parent.parent.parent

        return {
            "output_dir": str(project_root / "data" / "books"),
            "database_path": str(project_root / "data" / "library.db"),
            "temp_dir": str(project_root / "data" / "temp"),
            "chapter_detection": {
                "min_words_per_chapter": 500,
                "max_words_per_chapter": 50000,
                "patterns": [
                    r"^Chapter\s+(\d+)",
                    r"^CHAPTER\s+(\d+)",
                    r"^(\d+)\.\s+",
                    r"^Lesson\s+(\d+)",
                    r"^Module\s+(\d+)"
                ]
            },
            "section_splitting": {
                "enabled": True,
                "max_tokens_per_section": 15000,
                "min_tokens_per_section": 500,
                "section_patterns": [
                    r"^#{2,4}\s+.+$",
                    r"^\d+\.\d+(?:\.\d+)?\s+[A-Z].+$"
                ]
            },
            "text_cleaning": {
                "remove_headers": True,
                "remove_footers": True,
                "remove_page_numbers": True,
                "normalize_whitespace": True
            }
        }
    
    @property
    def output_dir(self):
        path = Path(self.config['output_dir'])
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    @property
    def database_path(self):
        path = Path(self.config['database_path'])
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    
    @property
    def temp_dir(self):
        path = Path(self.config['temp_dir'])
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    @property
    def chapter_detection(self):
        return self.config['chapter_detection']
    
    @property
    def text_cleaning(self):
        return self.config['text_cleaning']

    @property
    def section_splitting(self):
        return self.config.get('section_splitting', {
            'enabled': True,
            'max_tokens_per_section': 15000,
            'min_tokens_per_section': 500,
            'section_patterns': []
        })
