# Troubleshooting Guide

**Purpose**: Common issues and solutions for Echo-Node.

---

## Quick Diagnostics

Run these commands to check system status:

```bash
# Check audio devices
python -c "import sounddevice; print(sounddevice.query_devices())"

# Check GPU
nvidia-smi

# Check Ollama
curl http://localhost:11434/api/tags

# Check ports
netstat -tlnp | grep -E '3000|9001'
```

---

## Audio Issues

### "No microphone found"

**Symptoms**: Worker fails to start or can't capture audio

**Solutions**:
1. Check microphone is not muted (hardware or OS level)
2. List audio devices: `python -c "import sounddevice; print(sounddevice.query_devices())"`
3. Set device in config.yaml:
   ```yaml
   audio:
     device: "Built-in Microphone"
   ```
4. For WSL2, see docs/setup-wsl2.md

### "Audio sounds robotic/choppy"

**Symptoms**: TTS audio has artifacts

**Solutions**:
1. Increase chunk_size in config.yaml:
   ```yaml
   audio:
     chunk_size: 1024
   ```
2. Use hardware audio device instead of default
3. Check CPU usage (may need smaller models)

### "Echo during playback"

**Symptoms**: Speaker audio bleeds into microphone

**Solutions**:
1. Enable mic mute during playback:
   ```yaml
   echo_cancellation:
     mode: mute
   ```
2. Use headphones instead of speakers
3. Lower speaker volume
4. Move microphone further from speakers

---

## LLM Issues

### "Ollama not running"

**Symptoms**: Worker fails to connect to LLM

**Solutions**:
1. Start Ollama: `ollama serve`
2. Pull model: `ollama pull llama3.2:7b-q4_K_M`
3. Check Ollama is running: `curl http://localhost:11434/api/tags`

### "Model out of memory"

**Symptoms**: Worker crashes on LLM inference

**Solutions**:
1. Use smaller model (q4 instead of q8)
2. Reduce max_tokens in config
3. Enable VRAM monitoring
4. Close other GPU applications

### "API key rejected"

**Symptoms**: OpenAI/OpenRouter returns 401

**Solutions**:
1. Verify API key in config.yaml
2. Check key hasn't expired
3. Ensure no extra spaces in key
4. For OpenRouter, use correct base_url

---

## WebSocket Issues

### "Worker not connected"

**Symptoms**: Frontend shows "Worker unavailable"

**Solutions**:
1. Check worker is running: `ps aux | grep python`
2. Verify worker port (9001):
   ```bash
   netstat -tlnp | grep 9001
   ```
3. Check firewall allows localhost connections
4. Restart both worker and gateway

### "WebSocket connection failed"

**Symptoms**: Browser can't connect to gateway

**Solutions**:
1. Check gateway port (3000):
   ```bash
   netstat -tlnp | grep 3000
   ```
2. Clear browser cache
3. Use incognito window
4. Check browser console for errors

---

## Wake Word Issues

### "Wake word not detected"

**Symptoms**: System never activates

**Solutions**:
1. Lower threshold in config.yaml:
   ```yaml
   wake_word:
     threshold: 0.3
   ```
2. Use keyboard trigger as fallback
3. Ensure good audio quality
4. Train custom wake word if available

### "False wake word triggers"

**Symptoms**: System activates randomly

**Solutions**:
1. Increase threshold:
   ```yaml
   wake_word:
     threshold: 0.7
   ```
2. Increase cooldown:
   ```yaml
   wake_word:
     cooldown_ms: 5000
   ```
3. Reduce background noise

---

## VRAM/GPU Issues

### "Out of GPU memory"

**Symptoms**: CUDA errors, model loading fails

**Solutions**:
1. Use smaller models
2. Use quantization (q4 instead of q8)
3. Load models sequentially, not in parallel
4. Check VRAM: `nvidia-smi`
5. Close other GPU applications

### "No GPU detected"

**Symptoms**: Falls back to CPU, slow performance

**Solutions**:
1. Check NVIDIA driver: `nvidia-smi`
2. Install CUDA toolkit
3. Use CPU fallback in config:
   ```yaml
   stt:
     device: cpu
   tts:
     device: cpu
   ```

---

## Configuration Issues

### "Config validation failed"

**Symptoms**: Worker exits on startup

**Solutions**:
1. Check YAML syntax (no tabs!)
2. Verify required fields are present
3. Check provider names are valid
4. See config.example.yaml for reference

### "Provider not found"

**Symptoms**: Can't switch to requested provider

**Solutions**:
1. Verify provider is installed
2. Check provider name in config (lowercase)
3. Restart after changing providers

---

## Performance Issues

### "High latency (>2s)"

**Symptoms**: Slow response time

**Solutions**:
1. Use smaller/faster models
2. Enable streaming if available
3. Use GPU instead of CPU
4. Check network latency (cloud mode)
5. Reduce conversation history limit

### "High CPU usage"

**Symptoms**: System sluggish

**Solutions**:
1. Use GPU for inference
2. Reduce max_tokens
3. Use smaller models
4. Check for other resource-heavy processes

---

## Platform-Specific

### WSL2

- **Issue**: Audio not working
  - See docs/setup-wsl2.md for PipeWire/PulseAudio setup

- **Issue**: High latency
  - Use --share-ipc and --gpu flags with WSL

### Fedora Linux

- **Issue**: Audio permission denied
  - Add user to audio group: `sudo usermod -aG audio $USER`
  - Log out and back in

### macOS

- **Issue**: Microphone permission denied
  - System Preferences → Security & Privacy → Privacy → Microphone
  - Grant access to Terminal/Python

---

## Getting Help

If issues persist:

1. Check logs at debug level:
   ```yaml
   worker:
     log_level: debug
   ```
2. Run with verbose output
3. Open an issue at https://github.com/buttplug/voice-agent/issues
4. Include:
   - OS and version
   - GPU model
   - Relevant config section
   - Full error message
   - Logs

---

## Known Limitations

1. **Windows**: Native audio not supported (use WSL2)
2. **No GPU**: Falls back to CPU (slower)
3. **Cloud mode**: Requires internet, costs API fees
4. **ESP32**: Binary protocol is optional fallback
5. **Multiple sessions**: Single session only in MVP
