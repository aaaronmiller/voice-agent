"""
Echo-Node Pipeline Orchestrator — Assistant coordinator.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

import numpy as np


class Assistant:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.audio_config = AudioConfig(**config["audio"])
        self.mic = MicStream(self.audio_config)
        self.wake = WakeDetector(config.get("wake_word", {}))
        self.vad = SileroVad(config.get("vad", {}))
        self.recorder = Recorder(self.mic, self.vad, config.get("vad", {}))

        # STT
        stt_cfg = config.get("stt", {})
        stt_provider = stt_cfg.get("provider", "parakeet")
        if stt_provider == "faster-whisper":
            self.stt = FasterWhisperSTT(stt_cfg)
        else:
            self.stt = ParakeetSTT(stt_cfg)

        # Avatar
        try:
            from avatar import build as build_avatar
            self.avatar = build_avatar(config.get("avatar", {}))
            if hasattr(self.avatar, 'on_setting'):
                self.avatar.on_setting = self._on_setting_from_avatar
        except Exception as exc:
            print(f"[avatar] disabled: import failed: {exc}", flush=True)
            self.avatar = None

        # Backend (response generation) — will be initialised after config is fully parsed
        self._backend_provider: str = "hermes"
        self._backend: AgentBackend | None = None

        # Hotkeys (must be before speaker — speaker uses hotkey for interrupt)
        self.hotkey = KeyboardHotkey(config.get("hotkeys", {}))

        # Speech formatting
        self.speech_max_sentences = int(config.get("speech_format", {}).get("max_sentences", 4))
        self.speech_verbose = bool(config.get("speech_format", {}).get("verbose", False))

        # Speaker (TTS + barge-in, uses hotkey for Enter-to-interrupt)
        self.speaker = InterruptibleSpeaker(
            self.audio_config, self.vad,
            config.get("barge_in", {}),
            config.get("tts", {}),
            avatar=self.avatar,
            hotkey=self.hotkey,
        )

        # Wire debug data to avatar overlay
        def _debug_to_avatar(data: dict) -> None:
            if self.avatar is not None and hasattr(self.avatar, '_send'):
                self.avatar._send({"cmd": "debug_update", **data})
        self.speaker.debug_callback = _debug_to_avatar

        # Wire state to avatar
        self._avatar_state = _debug_to_avatar  # reuse same callback

        # ── Volume ducking state ──
        self._saved_volume: str | None = None
        self._last_state: str = "idle"
        try:
            import subprocess
            r = subprocess.run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"],
                               capture_output=True, text=True, timeout=2)
            if r.returncode == 0:
                self._has_wpctl = True
            else:
                self._has_wpctl = False
        except Exception:
            self._has_wpctl = False
        print(f"[sound] wpctl volume control: {'✓' if self._has_wpctl else '✗ (no-op)'}", flush=True)

        # Exit phrases
        assistant_cfg = config.get("assistant", {})
        self.exit_phrases = {str(p).lower() for p in assistant_cfg.get("exit_phrases", [])}
        system_prompt = str(assistant_cfg.get("system_prompt", ""))

        # Smart Router (agent_profiles)
        from echo_node.agent_profiles import get_all_agents, SmartRouter
        self._all_agents = get_all_agents()
        self.router = SmartRouter(self._all_agents, default="hermes")

        # Legacy LLM (direct)
        self.llm = LLMRouter(config.get("llm", {}), system_prompt)

        # Hermes native integration
        hermes_cfg = config.get("hermes", {})
        self.hermes = HermesIntegration(hermes_cfg) if hermes_cfg else None

        # Pi native integration
        pi_cfg = config.get("pi_agent", {})
        self.pi_agent = PiIntegration(pi_cfg) if pi_cfg else None

        # Performance
        self.performance = config.get("performance", {})
        self.stop = False

        # Idle model unloading: if no activity for N seconds, unload STT/TTS
        self._idle_unload = int(config.get("performance", {}).get("idle_unload_seconds", 300))
        self._last_activity = time.monotonic()
        self._last_idle_check = time.monotonic()

        # Post-turn cooldown: wait before re-enabling wake word detection
        self._post_turn_cooldown = float(config.get("performance", {}).get("post_turn_cooldown_seconds", 3))

        # Verbose toggle state (user can say "be verbose" to override)
        self._verbose_override = False

        # Conversation logger for audit & latency analysis
        self.logger = ConversationLogger(config.get("logging", {}))

        # Initialise the configured backend now that config is parsed
        self._init_backend(config)

    def _init_backend(self, config: dict[str, Any]) -> None:
        """Create or re-create the response-generation backend."""
        provider = str(config.get("backend", {}).get("provider", "hermes"))
        if provider not in REGISTRY:
            print(f"[backend] unknown provider {provider!r}, falling back to hermes", flush=True)
            provider = "hermes"
        self._backend_provider = provider
        try:
            self._backend = create_backend(provider, config)
            avail = self._backend.is_available()
            print(f"[backend] {provider} → {'✓' if avail else '✗'} {type(self._backend).__name__}", flush=True)
        except Exception as exc:
            print(f"[backend] failed to init {provider}: {exc}", flush=True)
            self._backend = None

    def _on_setting_from_avatar(self, cmd: str, kw: dict[str, Any]) -> None:
        """Handle settings changes forwarded from the avatar window popup."""
        if cmd == "set_backend":
            provider = kw.get("provider", "")
            if provider and provider != self._backend_provider and provider in REGISTRY:
                print(f"[settings] switching backend to {provider}", flush=True)
                self._backend_provider = provider
                self._init_backend(self.config)
                if self._backend and not self._backend.is_available():
                    print(f"[settings] backend {provider} is NOT available", flush=True)
        elif cmd == "set_volume":
            vol = kw.get("value", 1.0)
            try:
                import sounddevice as sd
                sd.default.device = self.audio_config.output_device
                os.environ["ECHO_NODE_VOLUME"] = str(vol)
            except Exception:
                pass
        elif cmd == "set_silence_seconds":
            val = kw.get("value", 0.4)
            self.vad.silence_seconds = float(val)
        elif cmd == "config":
            """Update a config section from the Cloud/Agent tabs."""
            section = kw.get("section", "")
            key = kw.get("key", "")
            value = kw.get("value")
            if section and key and value is not None:
                if key == "*" and isinstance(value, dict):
                    # Full section replacement (from profile load)
                    if section in self.config and isinstance(self.config[section], dict):
                        self.config[section].update(value)
                    else:
                        self.config[section] = dict(value)
                else:
                    self.config.setdefault(section, {})[key] = value
                print(f"[settings] config {section}.{key} = {value}", flush=True)
                # Apply immediately for certain sections
                if section == "llm" and key in ("provider", "base_url", "api_key", "model"):
                    self._init_backend(self.config)
                elif section == "assistant" and key == "wake_phrase":
                    if hasattr(self, '_reload_wake_word'):
                        self._reload_wake_word()
                elif section == "stt" and key == "provider":
                    if hasattr(self, '_reload_stt'):
                        self._reload_stt()
                elif section == "tts" and key == "provider":
                    if hasattr(self, '_reload_tts'):
                        self._reload_tts()
        elif cmd == "config_reload":
            """Full config reload (after profile load)."""
            print(f"[settings] config_reload triggered", flush=True)
            self._init_backend(self.config)
        elif cmd == "load_profile":
            name = kw.get("name", "")
            if name:
                print(f"[settings] profile loaded: {name}", flush=True)

    def run(self) -> int:
        signal.signal(signal.SIGINT, self._stop)
        signal.signal(signal.SIGTERM, self._stop)
        self.mic.open()
        self.hotkey.start()
        self._prewarm()
        print("[ready] say the wake phrase or press Enter/Escape", flush=True)
        try:
            while not self.stop:
                # Idle model unloading: if no activity for N seconds, free memory
                now = time.monotonic()
                if self._idle_unload > 0 and now - self._last_idle_check >= 5.0:
                    self._last_idle_check = now
                    if now - self._last_activity >= self._idle_unload:
                        self.stt.unload()
                        self.speaker.unload()
                # Check for hotkey triggers
                if self.hotkey.triggered():
                    event = self.hotkey.events.get_nowait() if not self.hotkey.events.empty() else ""
                    print(f"[hotkey] {event or 'manual'} trigger", flush=True)
                    rec = self.logger.new_turn(route="hotkey")
                    rec.t_wake = time.perf_counter()
                    self._last_activity = time.monotonic()
                    self.speaker.speak("Yes?", None, turn_rec=rec)
                    self._handle_turn(rec)
                    if self._post_turn_cooldown > 0:
                        time.sleep(self._post_turn_cooldown)
                    # Flush any stale hotkey events that accumulated during the
                    # turn (e.g., double-fire from multiple /dev/input devices).
                    while not self.hotkey.events.empty():
                        try:
                            self.hotkey.events.get_nowait()
                        except Exception:
                            break
                    continue

                # Normal wake word flow
                samples = self.mic.read()
                detected, name, score = self.wake.detect(samples)
                if not detected:
                    continue
                print(f"[wake] {name} {score:.2f}", flush=True)
                rec = self.logger.new_turn(route="wake")
                rec.t_wake = time.perf_counter()
                self._last_activity = time.monotonic()
                self.speaker.speak("Yes?", None, turn_rec=rec)
                self._handle_turn(rec)
                if self._post_turn_cooldown > 0:
                    time.sleep(self._post_turn_cooldown)
        finally:
            self.logger.close()
            self.hotkey.close()
            self.mic.close()
            if self.avatar is not None:
                self.avatar.shutdown()
        return 0

    def _send_state(self, state: str) -> None:
        """Push current assistant state to avatar and handle volume ducking.

        Volume ducking (via wpctl):
          idle:     restore saved volume
          listening: save volume (in case music is playing)
          responding: duck to 30% so user can hear the assistant
          (any other state): no change
        """
        # ── Push state to avatar ──
        if hasattr(self, '_avatar_state') and self._avatar_state:
            self._avatar_state({"cmd": "debug_update", "state": state})

        # ── Volume ducking ──
        if not getattr(self, '_has_wpctl', False):
            self._last_state = state
            return

        try:
            if state == "listening" and self._last_state != "listening":
                # Save current volume when we start listening
                if self._saved_volume is None:
                    r = subprocess.run(
                        ["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"],
                        capture_output=True, text=True, timeout=2,
                    )
                    if r.returncode == 0 and r.stdout.strip():
                        self._saved_volume = r.stdout.strip()
                        print(f"[duck] saved volume: {self._saved_volume}", flush=True)

            elif state == "responding" and self._last_state != "responding":
                # Duck to 30% when we start speaking
                subprocess.run(
                    ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "0.30"],
                    capture_output=True, timeout=2,
                )
                print(f"[duck] → 30%", flush=True)

            elif state == "idle" and self._last_state not in ("idle", ""):
                # Restore saved volume when idle
                if self._saved_volume is not None:
                    # Parse "Volume: 0.85" or "Volume: 0.85 [MUTED]"
                    parts = self._saved_volume.replace("Volume:", "").strip().split()
                    vol_val = parts[0] if parts else "1.0"
                    subprocess.run(
                        ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", vol_val],
                        capture_output=True, timeout=2,
                    )
                    print(f"[duck] restored → {vol_val}", flush=True)
                    self._saved_volume = None

        except Exception as exc:
            print(f"[duck] error: {exc}", flush=True)

        self._last_state = state

    def _handle_turn(self, rec: 'TurnRecord | None' = None) -> None:
        if rec is None:
            rec = self.logger.new_turn(route="internal")
            rec.t_wake = time.perf_counter()

        self._send_state("listening")
        rec.t_listen_start = time.perf_counter()
        wav_path = self.recorder.record_turn()
        rec.t_listen_done = time.perf_counter()
        if wav_path is None:
            rec.error = "no_speech"
            self.logger.end_turn(rec)
            self.speaker.speak("I did not hear speech.", None, turn_rec=rec)
            return

        self._send_state("transcribing")
        rec.t_stt_start = time.perf_counter()
        try:
            text = self.stt.transcribe(wav_path)
        finally:
            wav_path.unlink(missing_ok=True)
        rec.t_stt_done = time.perf_counter()
        rec.stt_model = str(self.config.get("stt", {}).get("model", ""))

        if not text:
            rec.error = "empty_transcription"
            self.logger.end_turn(rec)
            print("[stt] empty transcription", flush=True)
            self.speaker.speak("I could not transcribe that.", None, turn_rec=rec)
            return
        print(f"[you] {text}", flush=True)
        rec.user_text = text

        # Check exit phrases
        if text.lower().strip() in self.exit_phrases:
            rec.error = "exit_phrase"
            self.logger.end_turn(rec)
            self.speaker.speak("Stopping.", None, turn_rec=rec)
            self.stop = True
            return

        # Check verbose toggle commands
        lower = text.lower().strip()
        if lower in {"be verbose", "verbose mode", "verbose on"}:
            self._verbose_override = True
            self.speaker.speak("Verbose mode on. I will give longer replies.", None, turn_rec=rec)
            self.logger.end_turn(rec)
            return
        if lower in {"be concise", "concise mode", "verbose off", "normal mode"}:
            self._verbose_override = False
            self.speaker.speak("Concise mode on. Short replies.", None, turn_rec=rec)
            self.logger.end_turn(rec)
            return

        # Check for direct Hermes command: "ask hermes ..."
        if lower.startswith("ask hermes ") or lower.startswith("hermes, "):
            query = text[len("ask hermes "):] if lower.startswith("ask hermes ") else text[len("hermes, "):]
            self._handle_hermes_direct(query, rec)
            return

        # Check for direct Pi command: "ask pi ..."
        if lower.startswith("ask pi ") or lower.startswith("pi, "):
            query = text[len("ask pi "):] if lower.startswith("ask pi ") else text[len("pi, "):]
            self._handle_pi_direct(query, rec)
            return

        # ── Play "got it" chime as immediate auditory feedback ──
        # (non-blocking, does not use TTS — no latency added)
        _play_gotit_wav()

        self._send_state("working")
        rec.t_llm_start = time.perf_counter()
        system_prompt = str(self.config.get("assistant", {}).get("system_prompt", ""))

        # Use the configured backend if available (preferred path)
        backend: AgentBackend | None = getattr(self, '_backend', None)
        if backend and backend.is_available():
            rec.llm_model = self._backend_provider
            rec.route = self._backend_provider
            print(f"[backend] → {self._backend_provider} ({type(backend).__name__})", flush=True)

            def _token_to_text(stream):
                for token, is_first in stream:
                    if is_first:
                        rec.t_llm_first_token = time.perf_counter()
                    if token:
                        yield token
            try:
                stream = backend.chat_stream(text, system_prompt)
                interrupted, full_text = self.speaker.speak_stream(
                    _token_to_text(stream), self.mic, turn_rec=rec)
                answer = full_text
                rec.interrupted = interrupted
            except Exception as exc:
                print(f"[backend] stream failed: {exc}, falling back", flush=True)
                answer = backend.chat(text, system_prompt)
                answer = self._format_reply(answer)
                interrupted = self.speaker.speak(answer, self.mic, turn_rec=rec)
                rec.interrupted = interrupted
        else:
            # Fallback: SmartRouter → Hermes / LLMRouter
            route_key = self.router.classify(text)
            rec.route = route_key
            print(f"[router] {route_key} → {self.router.agents[route_key].name}", flush=True)

            if route_key == "hermes" and self.hermes and self.hermes.is_available():
                rec.llm_model = "hermes-agent"
                def _token_to_text(stream):
                    for token, is_first in stream:
                        if is_first:
                            rec.t_llm_first_token = time.perf_counter()
                        if token:
                            yield token
                interrupted, full_text = self.speaker.speak_stream(
                    _token_to_text(self.hermes.chat_stream(text, system_prompt)),
                    self.mic, turn_rec=rec)
                answer = full_text
                rec.interrupted = interrupted
            else:
                result = self.router.route(text, system_prompt)
                answer = result.text
                rec.llm_model = result.model
                answer = self._format_reply(answer)
                interrupted = self.speaker.speak(answer, self.mic, turn_rec=rec)
                rec.interrupted = interrupted

        rec.t_llm_done = time.perf_counter()
        self._send_state("responding")
        rec.assistant_text = answer
        truncated = answer[:200] + ("…" if len(answer) > 200 else "")
        print(f"[assistant/{rec.llm_model}] {truncated}", flush=True)
        self.logger.end_turn(rec)
        if rec.interrupted:
            self._handle_turn(rec)

    def _handle_hermes_direct(self, query: str, rec: 'TurnRecord | None' = None) -> None:
        """Direct Hermes invocation with guaranteed tool access."""
        if rec is None:
            rec = self.logger.new_turn(route="hermes_direct")
            rec.t_wake = time.perf_counter()
        if not self.hermes or not self.hermes.is_available():
            rec.error = "hermes_unavailable"
            self.logger.end_turn(rec)
            self.speaker.speak("Hermes is not running. Start the Hermes gateway first.", None, turn_rec=rec)
            return
        rec.user_text = query
        rec.llm_model = "hermes-agent"
        rec.t_llm_start = time.perf_counter()
        print(f"[hermes] {query}", flush=True)
        answer = self.hermes.chat(query, str(self.config.get("assistant", {}).get("system_prompt", "")))
        rec.t_llm_done = time.perf_counter()
        answer = self._format_reply(answer)
        rec.assistant_text = answer
        print(f"[hermes] {answer}", flush=True)
        interrupted = self.speaker.speak(answer, self.mic, turn_rec=rec)
        rec.interrupted = interrupted
        self.logger.end_turn(rec)
        if interrupted:
            self._handle_turn()

    def _handle_pi_direct(self, query: str, rec: 'TurnRecord | None' = None) -> None:
        """Direct Pi agent invocation."""
        if rec is None:
            rec = self.logger.new_turn(route="pi_direct")
            rec.t_wake = time.perf_counter()
        if not self.pi_agent or not self.pi_agent.is_available():
            rec.error = "pi_unavailable"
            self.logger.end_turn(rec)
            self.speaker.speak("Pi agent is not available.", None, turn_rec=rec)
            return
        rec.user_text = query
        rec.llm_model = "pi-agent"
        rec.t_llm_start = time.perf_counter()
        print(f"[pi] {query}", flush=True)
        answer = self.pi_agent.chat(query)
        rec.t_llm_done = time.perf_counter()
        answer = self._format_reply(answer)
        rec.assistant_text = answer
        print(f"[pi] {answer}", flush=True)
        interrupted = self.speaker.speak(answer, self.mic, turn_rec=rec)
        rec.interrupted = interrupted
        self.logger.end_turn(rec)
        if interrupted:
            self._handle_turn()

    def _format_reply(self, text: str) -> str:
        """Apply speech formatting to a reply."""
        from echo_node.speech_format import format_for_speech
        verbose = self._verbose_override or self.speech_verbose
        return format_for_speech(
            text,
            max_sentences=self.speech_max_sentences,
            verbose=verbose,
        )

    def _prewarm(self) -> None:
        started = time.perf_counter()
        if bool(self.performance.get("preload_stt", True)):
            try:
                self.stt.load()
            except Exception as exc:
                print(f"[warmup] STT preload failed: {exc}", flush=True)
        if bool(self.performance.get("warm_tts", True)):
            try:
                self.speaker.warm()
            except Exception as exc:
                print(f"[warmup] TTS warmup failed: {exc}", flush=True)
        if bool(self.performance.get("warm_backend", False)):
            self.llm.warmup()
        print(f"[timing] prewarm_total={time.perf_counter() - started:.2f}s", flush=True)

    def _stop(self, _signum: int, _frame: Any) -> None:
        self.stop = True


_GOTIT_WAV = Path(__file__).resolve().parent / "gotit.wav"


def _play_gotit_wav() -> None:
    """Play the 'got it' chime asynchronously via aplay.
    If the WAV doesn't exist or aplay fails, silently ignore."""
    if not _GOTIT_WAV.exists():
        return
    try:
        subprocess.Popen(
            ["aplay", "-q", str(_GOTIT_WAV)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        pass  # aplay not available
