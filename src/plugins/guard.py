import os
from typing import List

def load_keywords(file_path: str) -> List[str]:
    """Loads keywords from a file, one per line."""
    if not os.path.exists(file_path):
        keywords = []
    with open(file_path, "r", encoding="utf-8") as f:
        keywords = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    return keywords

class ContentGuard:
    def __init__(self, keywords_file: str = "src/static/bad_keywords.txt"):
        self.keywords = load_keywords(keywords_file)
        if not self.keywords:
            # Default keywords if the file is empty or not found
            self.keywords = ["贩毒"]

    def check(self, text: str) -> bool:
        """
        Checks if the text contains any sensitive keywords.
        Returns True if sensitive content is found, False otherwise.
        """
        if not text:
            return False
        text_lower = text.lower()
        for keyword in self.keywords:
            if keyword in text_lower:
                return True
        return False

# Global instance
content_guard = ContentGuard()
