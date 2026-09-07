import json
import asyncio
from typing import AsyncGenerator, List
from src.ingestion.base import BaseEmailSource
from src.core.models import EmailMessage

class MockStreamEmailSource(BaseEmailSource):
    def __init__(self, filepath: str, speed_multiplier: float = 1.0):
        self.filepath = filepath
        self.speed_multiplier = speed_multiplier
        self.messages: List[EmailMessage] = []
        self._is_paused = True  # ← was False, start paused and wait for Play

    async def connect(self) -> None:
        """Loads and sorts the JSON data into a chronological queue."""
        with open(self.filepath, 'r') as f:
            raw_data = json.load(f)

        flat_messages = []
        for email_group in raw_data.get('emails', []):
            for msg_data in email_group.get('messages', []):
                # Ensure the ISO datetime string is parseable
                msg_data['date_sent'] = msg_data['date_sent'].replace('Z', '+00:00')
                flat_messages.append(EmailMessage(**msg_data))

        # Sort strictly by chronological order across all threads
        self.messages = sorted(flat_messages, key=lambda x: x.date_sent)
        print(f"[Simulator] Loaded and sorted {len(self.messages)} messages.")

    def set_speed(self, multiplier: float):
        self.speed_multiplier = multiplier

    def toggle_pause(self, is_paused: bool):
        self._is_paused = is_paused

    async def stream_emails(self) -> AsyncGenerator[EmailMessage, None]:
        """Yields emails sequentially with a fixed rapid delay for testing."""
        if not self.messages:
            return

        for msg in self.messages:
            while self._is_paused:
                await asyncio.sleep(0.5)

            # Dynamic speed adjustment: 
            # If speed is 100x, we wait practically zero time. Otherwise scale normally.
            delay = max(0.05, 2.0 / self.speed_multiplier)
            await asyncio.sleep(delay)

            yield msg