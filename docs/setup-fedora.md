# Fedora 43 / GNOME / PipeWire Setup

Use Echo-Node v2 on native Fedora.

## Install

```bash
cd /home/misscheta/Downloads/voice-agent/v2
./install-fedora
```

The installer installs:

- `alsa-utils`
- `pipewire`
- `pipewire-alsa`
- `pipewire-pulseaudio`
- `wireplumber`
- `espeak-ng`
- `curl`
- `python3`
- `python3-pip`

It then runs `./setup.sh`, configures `audio.backend: alsa`, runs `./test.sh`,
captures one second from the microphone, and plays a Kokoro audio probe.

## Why ALSA On PipeWire

Echo-Node v2 currently uses `arecord` and `aplay` for Linux audio. Fedora 43
routes ALSA clients through PipeWire when `pipewire-alsa` is installed, so the
assistant can use stable CLI audio while GNOME still owns the normal PipeWire
audio graph.

## Verify Manually

```bash
arecord -L
aplay -L
arecord -q -D default -f S16_LE -c 1 -r 16000 -t raw -d 1 | wc -c
```

The one-second capture should print `32000` bytes.

Play a known WAV:

```bash
aplay -D default /tmp/echo-node-v2-fedora-test.wav
```

## Common Fixes

Restart user audio services:

```bash
systemctl --user restart pipewire pipewire-pulse wireplumber
```

Check that GNOME selected the intended microphone:

```bash
gnome-control-center sound
```

If GNOME sees the mic but `arecord` does not, reinstall the ALSA PipeWire
bridge:

```bash
sudo dnf reinstall pipewire-alsa alsa-utils
```

## Run

```bash
cd /home/misscheta/Downloads/voice-agent/v2
./run.sh
```
