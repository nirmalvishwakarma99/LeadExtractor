from abc import ABC, abstractmethod
from typing import List
from models import BusinessRecord

class BaseScraper(ABC):
    """Abstract interface defining the workflow for both Non-Image and Image scrapers."""

    @abstractmethod
    async def process_place(self, place_url: str) -> BusinessRecord:
        pass

    @abstractmethod
    async def run(self):
        pass