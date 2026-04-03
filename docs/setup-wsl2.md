# WSL2 Audio Setup for Echo-Node

**Purpose**: Configure audio routing in WSL2 for microphone access.

---

## Quick Check

```bash
# Check if audio server is available
pw-cli --version 2>/dev/null && echo "PipeWire found" || echo "No PipeWire"
pactl --version 2>/dev/null && echo "PulseAudio found" || echo "No PulseAudio"
```

---

## Fedora 43 WSLg (Audio Pre-configured)

Fedora 43 WSLg includes PipeWire by default. No additional setup needed.

```bash
# Verify PipeWire is running
pw-cli --version

# Test microphone
arecord -d 5 test.wav
aplay test.wav
```

If you hear your recording, audio is working. Skip to [Echo-Node Setup](#echo-node-setup).

---

## Ubuntu 24.04 WSL2 (Manual Setup)

Ubuntu WSL2 does not include audio by default. Install PulseAudio:

### Step 1: Install PulseAudio

```bash
sudo apt update
sudo apt install -y pulseaudio pulseaudio-utils
```

### Step 2: Configure PulseAudio

Edit or create `/etc/pulse/client.conf`:

```bash
sudo nano /etc/pulse/client.conf
```

Add these lines:

```text
default-server = 127.0.0.1
autospawn = yes
```

### Step 3: Start PulseAudio

```bash
pulseaudio --start
```

### Step 4: Test Audio

```bash
# List capture devices
arecord -l

# Test recording
arecord -d 5 -f cd test.wav
aplay test.wav
```

---

## Windows Host Configuration

### Check WSL2 Audio Settings

In Windows PowerShell (Admin):

```powershell
# Enable audio in WSL2
wsl --shutdown

# Edit WSL config (create if missing)
notepad $env:USERPROFILE\.wslconfig
```

Add or verify:

```ini
[wsl2]
audio=PipeWire
```

Save and restart WSL:

```powershell
wsl --shutdown
wsl
```

---

## Echo-Node Setup

Once audio is working at the system level:

```bash
cd echo-node

# Run setup
./setup.sh

# The setup script will:
# 1. Detect PipeWire or PulseAudio
# 2. Configure environment variables
# 3. Test audio capture
```

### Manual Configuration

If setup.sh doesn't detect audio:

```bash
# For PulseAudio
export PULSE_SERVER=127.0.0.1

# For PipeWire
export PIPEWIRE_REMOTE=default

# Test in Python
python3 -c "import sounddevice; print(sounddevice.query_devices())"
```

---

## Troubleshooting

### "No audio device found"

1. **Check WSL2 config**:
   ```bash
   cat ~/.wslconfig
   ```
   Ensure `audio=PipeWire` is present.

2. **Restart WSL**:
   ```powershell
   wsl --shutdown
   ```

3. **Reinstall audio packages**:
   ```bash
   sudo apt reinstall pulseaudio pulseaudio-utils
   pulseaudio --start
   ```

### "Device unavailable" or "Connection refused"

1. **Check PulseAudio is running**:
   ```bash
   pulseaudio --check && echo "Running" || pulseaudio --start
   ```

2. **Check Windows audio**:
   - Ensure Windows audio service is running
   - Check microphone privacy settings in Windows

3. **Try TCP connection**:
   ```bash
   export PULSE_SERVER=tcp:127.0.0.1
   ```

### Echo-Node Can't Access Mic

1. **List devices**:
   ```bash
   python3 -c "import sounddevice; print(sounddevice.query_devices())"
   ```

2. **Specify device in config.yaml**:
   ```yaml
   audio:
     device: "default"  # or specific device name
   ```

3. **Test with arecord**:
   ```bash
   arecord -l  # List devices
   arecord -D hw:0,0 -f cd test.wav  # Test specific device
   ```

---

## Performance Tips

### Reduce Latency

Edit `/etc/pulse/daemon.conf`:

```bash
sudo nano /etc/pulse/daemon.conf
```

Uncomment or add:

```text
default-fragments = 4
default-fragment-size-msec = 5
```

### Improve Quality

```text
resample-method = soxr-vhq
enable-lfe-remixing = no
```

---

## Next Steps

- [Setup Fedora](setup-fedora.md) - Native Fedora Linux
- [Setup macOS](setup-macos.md) - macOS audio
- [Quickstart](../quickstart.md) - Get started with Echo-Node
