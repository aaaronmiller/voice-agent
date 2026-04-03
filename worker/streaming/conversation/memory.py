"""
Conversation Memory for Echo-Node

Maintains a sliding window of conversation history (default: 15 turns).
No cross-session persistence.
"""

from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime
import uuid


@dataclass
class Turn:
    """Single conversation turn."""
    turn_number: int
    user_transcript: str
    assistant_response: str
    timestamp: float = field(default_factory=datetime.now().timestamp)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for LLM context."""
        return {
            'user': self.user_transcript,
            'assistant': self.assistant_response,
        }


class ConversationMemory:
    """
    Sliding window conversation memory.
    
    Maintains up to max_turns turns of conversation history.
    Oldest turns are evicted when the limit is exceeded.
    """

    def __init__(self, max_turns: int = 15, session_id: Optional[str] = None):
        """
        Initialize conversation memory.
        
        Args:
            max_turns: Maximum number of turns to retain
            session_id: Optional session identifier
        """
        self.max_turns = max_turns
        self.session_id = session_id or str(uuid.uuid4())
        self._turns: List[Turn] = []
        self._turn_counter = 0

    def add_turn(self, user_transcript: str, assistant_response: str) -> Turn:
        """
        Add a new turn to conversation history.
        
        Args:
            user_transcript: User's spoken input
            assistant_response: Assistant's text response
        
        Returns:
            The created Turn object
        """
        self._turn_counter += 1
        
        turn = Turn(
            turn_number=self._turn_counter,
            user_transcript=user_transcript,
            assistant_response=assistant_response,
        )
        
        self._turns.append(turn)
        
        # Evict oldest turns if exceeding limit
        while len(self._turns) > self.max_turns:
            self._turns.pop(0)
        
        return turn

    def get_turns(self) -> List[Turn]:
        """Get all turns in memory (oldest to newest)."""
        return self._turns.copy()

    def get_recent(self, count: int) -> List[Turn]:
        """
        Get the N most recent turns.
        
        Args:
            count: Number of turns to retrieve
        
        Returns:
            List of recent turns (oldest to newest within the subset)
        """
        return self._turns[-count:] if count < len(self._turns) else self._turns.copy()

    def build_context_messages(self) -> List[dict]:
        """
        Build messages list for LLM context.
        
        Returns:
            List of message dicts with role and content
        """
        messages = []
        
        for turn in self._turns:
            messages.append({'role': 'user', 'content': turn.user_transcript})
            messages.append({'role': 'assistant', 'content': turn.assistant_response})
        
        return messages

    def get_turn_by_number(self, turn_number: int) -> Optional[Turn]:
        """
        Get a specific turn by number.
        
        Args:
            turn_number: The turn number to find
        
        Returns:
            Turn object or None if not found
        """
        for turn in self._turns:
            if turn.turn_number == turn_number:
                return turn
        return None

    def contains_reference(self, text: str) -> bool:
        """
        Check if text references something in conversation history.
        
        Simple heuristic: checks for turn numbers or quoted text.
        
        Args:
            text: Text to check for references
        
        Returns:
            True if likely referencing prior conversation
        """
        # Check for turn number references ("earlier you said", "in turn 5", etc.)
        if any(phrase in text.lower() for phrase in [
            'earlier', 'before', 'previously', 'you said', 'you mentioned',
            'turn', 'question', 'answer'
        ]):
            return True
        
        return False

    def clear(self) -> None:
        """Clear all conversation history."""
        self._turns.clear()
        self._turn_counter = 0

    def __len__(self) -> int:
        """Get number of turns in memory."""
        return len(self._turns)

    def is_empty(self) -> bool:
        """Check if memory is empty."""
        return len(self._turns) == 0

    @property
    def turn_count(self) -> int:
        """Get total turns processed this session."""
        return self._turn_counter
