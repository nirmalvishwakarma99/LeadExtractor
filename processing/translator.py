import re
from deep_translator import GoogleTranslator

class MultilingualHandler:
    def __init__(self):
        self.translator = GoogleTranslator(source="auto", target="en")

    def is_mostly_ascii(self, text: str) -> bool:
        if not text:
            return True
        non_ascii = len([c for c in text if ord(c) > 127])
        return (non_ascii / len(text)) < 0.15

    def translate_text(self, text: str) -> str:
        if not text or self.is_mostly_ascii(text):
            return text
        try:
            # Preserve URLs and email patterns intact
            if "http://" in text or "https://" in text or "@" in text:
                return text
            translated = self.translator.translate(text)
            return translated if translated else text
        except Exception:
            return text