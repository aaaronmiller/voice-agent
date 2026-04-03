"""
5-State Pipeline State Machine for Echo-Node

States: DORMANT → TRIGGERED → LISTENING → PROCESSING → SPEAKING → DORMANT
                                              ↑              ↓
                                              └──(barge-in)──┘

All state transitions originate from the Python worker and are emitted
as WebSocket events to the gateway.
"""

from enum import Enum
from typing import Callable
import asyncio


class State(Enum):
    """Pipeline states."""
    DORMANT = "dormant"           # Waiting for wake word
    TRIGGERED = "triggered"       # Wake word detected, playing activation sound
    LISTENING = "listening"       # VAD active, capturing audio
    PROCESSING = "processing"     # STT→LLM→TTS pipeline running
    SPEAKING = "speaking"         # TTS playback active


class StateMachine:
    """
    State machine for voice pipeline.
    
    Thread-safe state transitions with validation.
    All transitions are logged and emitted to connected clients.
    """

    def __init__(self, on_transition: Callable[[State, State], None] | None = None):
        """
        Initialize state machine.
        
        Args:
            on_transition: Optional callback invoked on each state transition
        """
        self._state = State.DORMANT
        self._on_transition = on_transition
        self._lock = asyncio.Lock()

    @property
    def state(self) -> State:
        """Get current state."""
        return self._state

    @property
    def state_name(self) -> str:
        """Get current state name (lowercase)."""
        return self._state.value

    async def transition(self, target: State) -> bool:
        """
        Attempt state transition.
        
        Args:
            target: Target state to transition to
        
        Returns:
            True if transition was valid and completed, False if invalid
        """
        async with self._lock:
            if not self._is_valid(self._state, target):
                return False
            
            old = self._state
            self._state = target
            
            if self._on_transition:
                self._on_transition(old, target)
            
            return True

    def _is_valid(self, current: State, target: State) -> bool:
        """
        Check if state transition is valid.
        
        Valid transitions:
            DORMANT → TRIGGERED
            TRIGGERED → LISTENING
            LISTENING → PROCESSING, DORMANT (timeout)
            PROCESSING → SPEAKING, DORMANT (error)
            SPEAKING → DORMANT, LISTENING (barge-in)
        """
        valid_transitions: dict[State, set[State]] = {
            State.DORMANT: {State.TRIGGERED},
            State.TRIGGERED: {State.LISTENING},
            State.LISTENING: {State.PROCESSING, State.DORMANT},
            State.PROCESSING: {State.SPEAKING, State.DORMANT},
            State.SPEAKING: {State.DORMANT, State.LISTENING},
        }
        return target in valid_transitions.get(current, set())

    def is_active(self) -> bool:
        """Check if pipeline is actively processing (not DORMANT)."""
        return self._state != State.DORMANT

    def is_listening(self) -> bool:
        """Check if pipeline is in LISTENING state."""
        return self._state == State.LISTENING

    def is_speaking(self) -> bool:
        """Check if pipeline is in SPEAKING state."""
        return self._state == State.SPEAKING

    async def reset(self) -> None:
        """Force reset to DORMANT state."""
        async with self._lock:
            self._state = State.DORMANT
