#!/usr/bin/env python3
"""
Voice Activity Detection controller for AnythingLLM on macOS
Automatically clicks the microphone button when speech is detected
"""

import pyaudio
import webrtcvad
import subprocess
import threading
import time
import signal
import sys
import speech_recognition as sr
from collections import deque

class AnythingLLMVAD:
    def __init__(self):
        self.vad = webrtcvad.Vad(2)  # Aggressiveness 0-3 (2 = moderate)
        self.speaking_threshold = 6   # Frames needed to trigger (adjust as needed)
        self.silence_threshold = 15   # Frames needed to stop (longer to avoid cutting off)
        self.min_speech_duration = 0.5  # Minimum seconds of speech before triggering
        self.debounce_time = 1.0     # Seconds to wait between triggers
        
        self.last_trigger_time = 0
        self.audio = None
        self.stream = None
        self.running = False
        
        # Browser and window detection
        self.browser_name = "Chrome"  # Change to "Firefox", "Safari", etc. if needed
        
        # Speech recognition for keyword detection
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        
        # Keyword commands
        self.keywords = {
            'send': self.send_message,
            'clear': self.clear_chat,
            'new chat': self.new_chat,
            'scroll up': self.scroll_up,
            'scroll down': self.scroll_down,
            'cancel': self.cancel_input,
            'delete': self.delete_last_word,
            'undo': self.undo_last_action,
            'copy': self.copy_response,
            'paste': self.paste_text,
            'stop listening': self.stop_listening,
            'start listening': self.start_listening
        }
        
        # State management
        self.listening_mode = True
        self.last_speech_text = ""
        
    def find_anythingllm_window(self):
        """Find the AnythingLLM browser window"""
        try:
            # Get list of windows for the browser
            script = f'''
            tell application "System Events"
                tell process "{self.browser_name}"
                    get name of every window
                end tell
            end tell
            '''
            result = subprocess.run(['osascript', '-e', script], 
                                  capture_output=True, text=True)
            
            windows = result.stdout.strip().split(', ')
            for window in windows:
                if 'AnythingLLM' in window or 'localhost' in window:
                    return window.strip('"')
            
            print(f"Warning: AnythingLLM window not found in {self.browser_name}")
            return None
            
        except Exception as e:
            print(f"Error finding window: {e}")
            return None
    
    def trigger_dictation(self):
        """Simulate double-Fn press to activate macOS dictation"""
        current_time = time.time()
        if current_time - self.last_trigger_time < self.debounce_time:
            return
        
        try:
            # Make sure AnythingLLM is in focus
            script = f'''
            tell application "{self.browser_name}" to activate
            delay 0.2
            tell application "System Events"
                -- Simulate double Fn press (key code 63 is Fn key)
                key code 63
                delay 0.1
                key code 63
            end tell
            '''
            
            subprocess.run(['osascript', '-e', script], check=True)
            self.last_trigger_time = current_time
            print("🎤 Dictation activated!")
            
        except subprocess.CalledProcessError as e:
            print(f"Error activating dictation: {e}")
    
    def listen_for_keywords(self, audio_data):
        """Process speech to detect keywords and execute commands"""
        try:
            # Convert audio to text
            text = self.recognizer.recognize_google(audio_data).lower()
            self.last_speech_text = text
            print(f"Heard: '{text}'")
            
            # Check for keyword commands
            command_executed = False
            for keyword, action in self.keywords.items():
                if keyword in text:
                    print(f"🎯 Executing command: {keyword}")
                    action()
                    command_executed = True
                    break
            
            # If no command found, proceed with normal dictation
            if not command_executed and self.listening_mode:
                self.trigger_dictation()
                
        except sr.UnknownValueError:
            print("Could not understand audio")
        except sr.RequestError as e:
            print(f"Error with speech recognition: {e}")
    
    # Command implementations
    def send_message(self):
        """Send the current message"""
        script = '''
        tell application "System Events"
            key code 36  -- Enter key
        end tell
        '''
        subprocess.run(['osascript', '-e', script])
        print("📤 Message sent!")
    
    def clear_chat(self):
        """Clear the input field"""
        script = '''
        tell application "System Events"
            key code 0 using {command down}  -- Cmd+A (select all)
            delay 0.1
            key code 51  -- Delete
        end tell
        '''
        subprocess.run(['osascript', '-e', script])
        print("🗑️ Input cleared!")
    
    def new_chat(self):
        """Start a new chat (Cmd+N or equivalent)"""
        script = '''
        tell application "System Events"
            key code 45 using {command down}  -- Cmd+N
        end tell
        '''
        subprocess.run(['osascript', '-e', script])
        print("🆕 New chat started!")
    
    def scroll_up(self):
        """Scroll up in the chat"""
        script = '''
        tell application "System Events"
            key code 126  -- Up arrow
            key code 126
            key code 126
        end tell
        '''
        subprocess.run(['osascript', '-e', script])
    
    def scroll_down(self):
        """Scroll down in the chat"""
        script = '''
        tell application "System Events"
            key code 125  -- Down arrow
            key code 125
            key code 125
        end tell
        '''
        subprocess.run(['osascript', '-e', script])
    
    def cancel_input(self):
        """Cancel current input"""
        script = '''
        tell application "System Events"
            key code 53  -- Escape key
        end tell
        '''
        subprocess.run(['osascript', '-e', script])
        print("❌ Input cancelled!")
    
    def delete_last_word(self):
        """Delete the last word"""
        script = '''
        tell application "System Events"
            key code 51 using {option down}  -- Option+Delete
        end tell
        '''
        subprocess.run(['osascript', '-e', script])
        print("🔙 Last word deleted!")
    
    def undo_last_action(self):
        """Undo last action"""
        script = '''
        tell application "System Events"
            key code 6 using {command down}  -- Cmd+Z
        end tell
        '''
        subprocess.run(['osascript', '-e', script])
        print("↩️ Undone!")
    
    def copy_response(self):
        """Copy the last AI response"""
        script = '''
        tell application "System Events"
            key code 8 using {command down}  -- Cmd+C
        end tell
        '''
        subprocess.run(['osascript', '-e', script])
        print("📋 Response copied!")
    
    def paste_text(self):
        """Paste from clipboard"""
        script = '''
        tell application "System Events"
            key code 9 using {command down}  -- Cmd+V
        end tell
        '''
        subprocess.run(['osascript', '-e', script])
        print("📋 Text pasted!")
    
    def stop_listening(self):
        """Stop voice recognition"""
        self.listening_mode = False
        print("🔇 Voice recognition paused")
    
    def start_listening(self):
        """Resume voice recognition"""
        self.listening_mode = True
        print("🔊 Voice recognition resumed")
    
    def setup_audio(self):
        """Initialize audio stream"""
        try:
            self.audio = pyaudio.PyAudio()
            
            # Find the default input device
            default_device = self.audio.get_default_input_device_info()
            print(f"Using microphone: {default_device['name']}")
            
            self.stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                frames_per_buffer=320,  # 20ms chunks
                input_device_index=default_device['index']
            )
            
            return True
            
        except Exception as e:
            print(f"Error setting up audio: {e}")
            return False
    
    def cleanup(self):
        """Clean up audio resources"""
        self.running = False
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        if self.audio:
            self.audio.terminate()
        print("\nCleaned up audio resources")
    
    def process_speech_segment(self, frames):
        """Process accumulated speech frames for keyword detection"""
        try:
            # Combine frames into audio data
            audio_data = b''.join(frames)
            
            # Convert to format suitable for speech recognition
            audio_np = sr.AudioData(audio_data, sample_rate=16000, sample_width=2)
            
            # Run keyword detection in separate thread to avoid blocking
            threading.Thread(target=self.listen_for_keywords, args=(audio_np,), daemon=True).start()
            
        except Exception as e:
            print(f"Error processing speech: {e}")
    
    def monitor_voice(self):
        """Main voice monitoring loop with keyword detection"""
        if not self.setup_audio():
            return
        
        print("Voice Activity Detection with Keyword Commands started!")
        print(f"Using browser: {self.browser_name}")
        print("\nAvailable commands:")
        for keyword in self.keywords.keys():
            print(f"  • '{keyword}'")
        print("\nSpeak to trigger commands or dictation...")
        print("Press Ctrl+C to stop")
        
        speaking_frames = 0
        silence_frames = 0
        currently_recording = False
        speech_frames = []  # Store frames for keyword processing
        
        self.running = True
        
        try:
            while self.running:
                # Read audio frame
                frame = self.stream.read(320, exception_on_overflow=False)
                
                # Check if frame contains speech
                try:
                    is_speech = self.vad.is_speech(frame, 16000)
                except:
                    continue
                
                if is_speech:
                    speaking_frames += 1
                    silence_frames = 0
                    speech_frames.append(frame)
                    
                    if speaking_frames == 1:  # First frame of speech
                        print("🎤 Speech detected...")
                        speech_frames = [frame]  # Reset frame collection
                else:
                    silence_frames += 1
                    if speaking_frames > 0:  # Was speaking, now silent
                        speaking_frames = 0
                
                # Process speech when we have enough frames and detect silence
                if (len(speech_frames) >= self.speaking_threshold and 
                    silence_frames >= 5 and  # Shorter silence for keyword detection
                    not currently_recording):
                    
                    print("🔍 Processing speech for keywords...")
                    self.process_speech_segment(speech_frames)
                    currently_recording = True
                    speech_frames = []
                    
                # Reset state after longer silence
                elif silence_frames >= self.silence_threshold and currently_recording:
                    currently_recording = False
                    
        except KeyboardInterrupt:
            print("\nShutting down...")
        except Exception as e:
            print(f"Error in monitoring loop: {e}")
        finally:
            self.cleanup()

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    print("\nReceived interrupt signal...")
    sys.exit(0)

def main():
    # Set up signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    
    print("AnythingLLM Voice Activity Detection Controller")
    print("=" * 50)
    
    # Check if we can find AnythingLLM
    vad = AnythingLLMVAD()
    window = vad.find_anythingllm_window()
    if window:
        print(f"Found AnythingLLM window: {window}")
    
    # Instructions are printed, but we no longer wait for input
    print("\nBefore starting:")
    print("1. Make sure AnythingLLM is open in your browser")
    print("2. Navigate to a chat where you can see the microphone button")
    print("3. Test that clicking the mic button manually works")
    
    # Script now starts automatically
    print("\nStarting voice detection automatically...")
    vad.monitor_voice()


if __name__ == "__main__":
    main()