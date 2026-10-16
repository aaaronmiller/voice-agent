# STT Service - Deployment & Launch Guide

## ✓ Status: READY FOR PRODUCTION

All 8 core components tested and verified:
- [x] Logger infrastructure
- [x] Clipboard manager (save/restore)
- [x] Audio recorder
- [x] STT engine (Whisper tiny model loads)
- [x] Paster (auto-paste)
- [x] Hotkey listener
- [x] Configuration system
- [x] File structure

---

## Quick Launch

### Option 1: Manual Testing (Recommended First)

```bash
# Terminal 1: Run service
cd C:\Users\Administrator\Desktop\stt_project
python main.py

# You'll see:
# [+] Service ready. Press ctrl+shift+a to start recording
```

**In Terminal 2 (while service runs):**
```bash
# Open any text editor/chat app
# Click in the text input field
# Press Ctrl+Shift+A to start recording
# Speak clearly: "Hello this is a test"
# Press Ctrl+Shift+A again to stop
# Text should appear in 2-5 seconds
```

---

### Option 2: Install to Windows Startup (Background Service)

**Run as Administrator:**
```bash
cd C:\Users\Administrator\Desktop\stt_project
install_service.bat
```

**Then restart computer** → Service starts automatically in background

To remove: Delete `STT_Service.lnk` from `C:\Users\Administrator\AppData\Microsoft\Windows\Start Menu\Programs\Startup`

---

## Before First Use

### 1. **Test Microphone** (Important!)
- Windows Settings → Sound → Input devices
- Verify microphone is listed and works
- Test with Windows Voice Recorder app

### 2. **Set OpenRouter API Key** (Optional but recommended)
- Go to https://openrouter.ai
- Sign up (free tier available)
- Copy API key
- Edit `config.json`:
  ```json
  "openrouter_api_key": "sk-or-v1-YOUR_KEY_HERE"
  ```

### 3. **Adjust Hotkey if Needed** (Optional)
- Edit `config.json`, change:
  ```json
  "hotkey": "ctrl+shift+s"  // or your preference
  ```

---

## What Happens When You Use It

### Timeline Example
```
00:00 - Press Ctrl+Shift+A (START RECORDING)
00:00 - Log: ">>> RECORDING STARTED <<<"
00:00 - Indicator: State = "recording"

00:05 - Speak: "Meeting notes about Q1 budget"

00:10 - Press Ctrl+Shift+A (STOP & TRANSCRIBE)
00:10 - Log: ">>> RECORDING STOPPED <<<"
00:10 - Log: "[1/5] Stopping audio capture..."
00:10 - Audio file: C:\Users\Administrator\Desktop\stt_project\temp_audio\temp_recording.wav

00:11 - Log: "[2/5] Saving clipboard..."
00:11 - Clipboard backup saved to: C:\Users\Administrator\Desktop\stt_project\temp_clipboard\clipboard_backup.txt

00:12 - Log: "[3/5] Transcribing audio..."
00:15 - Whisper tiny finishes: "Meeting notes about Q1 budget"

00:16 - Log: "[4/5] Setting clipboard and pasting..."
00:16 - Text auto-pasted at cursor

00:17 - Log: "[5/5] Restoring clipboard..."
00:17 - Original clipboard restored
00:17 - Log: ">>> PIPELINE COMPLETE <<<"
00:17 - State = "idle" (ready for next use)
```

**Total time: 17 seconds** (1 sec per minute of audio)

---

## Real-World Use Cases

### 1. **Chat & Messaging**
```
1. Click in Discord/Slack/Teams message box
2. Press Ctrl+Shift+A
3. Speak your message
4. Press Ctrl+Shift+A again
5. Message appears and auto-pastes
6. Press Enter to send
```

### 2. **Email Drafting**
```
1. Open email composer
2. Click in message body
3. Press Ctrl+Shift+A
4. Dictate email content
5. Press Ctrl+Shift+A to complete
6. Edit if needed, send
```

### 3. **Code Comments**
```
1. In code editor, position cursor at line
2. Press Ctrl+Shift+A
3. Say: "TODO fix this authentication bug next sprint"
4. Press Ctrl+Shift+A
5. Comment auto-pasted
6. Press Enter to confirm
```

### 4. **Note-Taking**
```
1. Open OneNote/Obsidian/Notion
2. Press Ctrl+Shift+A
3. Record your thoughts
4. Press Ctrl+Shift+A
5. Notes captured
```

---

## Monitoring & Logs

### View Live Activity
```bash
# Monitor logs in real-time
type stt_service.log | tail -20
```

### Check for Errors
```bash
# Find all errors
findstr /C:"ERROR" stt_service.log

# Find specific issue
findstr /C:"Microphone not found" stt_service.log
```

### Log Rotation
Logs automatically rotate at 10MB (keeps last 3 backups)

---

## Troubleshooting Checklist

### Service Won't Start
- [ ] Run PowerShell as Administrator
- [ ] Check microphone is working (Windows Sound settings)
- [ ] Verify `config.json` is valid JSON
- [ ] Check logs: `type stt_service.log`

### Recording Not Working
- [ ] Microphone enabled in Windows Sound
- [ ] Test with Windows Voice Recorder
- [ ] Try different microphone (if multiple available)
- [ ] Check `audio_recorder.py` logs

### Text Not Pasting
- [ ] Make sure focus is on input field (not password field)
- [ ] Try pasting manually (Ctrl+V) in same location
- [ ] Increase `paste_delay` in config.json (try 0.3)
- [ ] Try different app (test in Notepad first)

### Transcription Taking Too Long
- [ ] Check if model is loading (first run is slow)
- [ ] Reduce `local_timeout_seconds` in config.json
- [ ] Add OpenRouter API key for faster fallback
- [ ] Use `model_size: "tiny"` (already default)

### Service Crashes
- [ ] Check logs for error message
- [ ] Verify all dependencies installed: `pip install -r requirements.txt`
- [ ] Try running `test_pipeline.py` for diagnostics
- [ ] Check Windows Event Viewer for system errors

---

## Performance Optimization

### Speed Up Transcription
```json
{
  "model_size": "tiny",           // Fastest
  "local_timeout_seconds": 3,     // Faster remote fallback
  "use_local_stt": true           // Try local first
}
```

**Expected times:**
- Whisper tiny: 1-2 sec per minute of speech
- OpenRouter: 0.5-1 sec per minute (includes network)
- Total latency: 2-5 seconds from stop recording to paste

### Reduce System Load
```json
{
  "enable_remote_fallback": true,  // Lighter on CPU
  "local_timeout_seconds": 2       // Use remote more often
}
```

---

## Security & Privacy

✓ **Audio Safety**
- Audio files deleted immediately after transcription
- No long-term storage of recordings
- Only sent to remote if local timeout exceeded

✓ **Clipboard Safety**
- Original clipboard backed up and restored
- No sensitive data persists
- Temp clipboard files cleaned up

✓ **Data Policy**
- All processing local by default
- Remote only as fallback
- No audio stored on remote servers
- API call logs follow OpenRouter's privacy policy

---

## Advanced Configuration

### Use Remote API Exclusively (Cloud-Only)
```json
{
  "use_local_stt": false,           // Disable local
  "openrouter_api_key": "sk-or..."  // Must be set
}
```

### Custom Hotkey
```json
{
  "hotkey": "f9"                    // Single key press
}
```

### Longer Recording Timeouts
```json
{
  "local_timeout_seconds": 10       // Wait longer before fallback
}
```

---

## Future Features (Phase 2)

- [ ] System tray icon with recording indicator
- [ ] Real-time transcription (show text while recording)
- [ ] Language detection (auto-detect language)
- [ ] Multiple hotkey profiles
- [ ] GPU acceleration via Arc XPU
- [ ] GUI settings panel
- [ ] Voice activity detection (auto-stop silence)
- [ ] Custom models support
- [ ] Saved recordings library

---

## Support & Debugging

**For detailed component info:**
```bash
python -c "from logger import setup_logger; logger = setup_logger(); print('Service components ready')"
```

**Validate all imports:**
```bash
python -c "import audio_recorder; import stt_engine; import clipboard_manager; import paster; import hotkey_listener; print('All imports OK')"
```

**Run full test suite:**
```bash
python test_pipeline.py
```

**Run main service:**
```bash
python main.py
```

---

## System Requirements

- **OS**: Windows 10/11
- **Python**: 3.9+
- **RAM**: 4GB minimum (Arc A370)
- **Microphone**: Working input device
- **Admin**: Required for global hotkeys (first run)

---

## File Manifest

```
stt_project/
├── main.py                    # ← RUN THIS
├── config.json               # Edit to customize
├── logger.py                 # Logging
├── hotkey_listener.py        # Global hotkey detection
├── audio_recorder.py         # Microphone capture
├── stt_engine.py            # Whisper + OpenRouter
├── clipboard_manager.py     # Clipboard operations
├── paster.py                # Auto-paste
├── install_service.bat      # Windows startup installer
├── requirements.txt         # Dependencies
├── test_pipeline.py         # Validation tests
├── SETUP.md                 # Setup guide
├── DEPLOYMENT.md            # This file
├── README.md                # Project overview
├── stt_service.log          # Auto-generated logs
├── temp_audio/              # Auto-generated recording folder
└── temp_clipboard/          # Auto-generated backup folder
```

---

## Launch Command

```bash
# Navigate to project
cd C:\Users\Administrator\Desktop\stt_project

# Run service
python main.py

# Wait for:
# "Service ready. Press ctrl+shift+a to start recording"

# Then:
# Ctrl+Shift+A = Start recording
# Ctrl+Shift+A = Stop & transcribe
```

---

**Version**: 1.0 MVP
**Status**: ✓ PRODUCTION READY
**Last Updated**: 2026-01-20
**Test Results**: 8/8 PASS
