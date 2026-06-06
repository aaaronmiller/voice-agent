param(
    [switch]$InstallPython
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host "Echo-Node v2 Windows installer"
Write-Host "=============================="

function Get-Python311 {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        & py -3.11 --version *> $null
        if ($LASTEXITCODE -eq 0) {
            return @("py", "-3.11")
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        $version = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        if ($version -eq "3.11") {
            return @("python")
        }
    }

    return $null
}

function Invoke-BasePython {
    param([string[]]$ArgsList)
    $exe = $PythonCmd[0]
    $baseArgs = @()
    if ($PythonCmd.Length -gt 1) {
        $baseArgs = @($PythonCmd[1..($PythonCmd.Length - 1)])
    }
    & $exe @baseArgs @ArgsList
}

$PythonCmd = Get-Python311
if (-not $PythonCmd) {
    if ($InstallPython) {
        $winget = Get-Command winget -ErrorAction SilentlyContinue
        if (-not $winget) {
            throw "Python 3.11 not found and winget is unavailable. Install Python 3.11 manually."
        }
        Write-Host "Installing Python 3.11 with winget..."
        winget install --id Python.Python.3.11 -e --source winget
        $PythonCmd = Get-Python311
    }
}

if (-not $PythonCmd) {
    throw "Python 3.11 not found. Install Python 3.11 or rerun with -InstallPython."
}

Write-Host "Creating Python virtual environment..."
Invoke-BasePython @("-m", "venv", ".venv")

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    throw "Virtual environment python not found at $VenvPython"
}

Write-Host "Installing Windows Python dependencies..."
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r requirements-windows.txt

Write-Host "Downloading OpenWakeWord resources..."
& $VenvPython -c "from openwakeword.utils import download_models; download_models(model_names=['hey_jarvis'])"

New-Item -ItemType Directory -Force -Path "models\kokoro" | Out-Null

function Download-IfMissing($Url, $OutFile) {
    if (Test-Path $OutFile) {
        Write-Host "Already present: $OutFile"
        return
    }
    Write-Host "Downloading $OutFile"
    Invoke-WebRequest -Uri $Url -OutFile $OutFile
}

Download-IfMissing "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx" "models\kokoro\kokoro-v1.0.onnx"
Download-IfMissing "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin" "models\kokoro\voices-v1.0.bin"

if (-not (Test-Path "config.yaml")) {
    Copy-Item "config.example.yaml" "config.yaml"
}

Write-Host "Configuring v2 for native Windows sounddevice audio..."
$ConfigureScript = @'
from pathlib import Path
import yaml

path = Path("config.yaml")
config = yaml.safe_load(path.read_text()) or {}
audio = config.setdefault("audio", {})
audio["backend"] = "sounddevice"
audio["arecord_device"] = "default"
audio["playback_device"] = "default"
audio["input_device"] = None
audio["output_device"] = None
config.setdefault("wake_word", {})["pretrained"] = ["hey_jarvis"]
config["wake_word"]["model_paths"] = []
path.write_text(yaml.safe_dump(config, sort_keys=False))
'@
$ConfigureScript | & $VenvPython -

Write-Host "Running import, wake, VAD, STT, and Kokoro checks..."
$CheckScript = @'
from pathlib import Path
import os
from assistant_v2 import WakeDetector, SileroVad, ParakeetSTT, KokoroTTS

WakeDetector({"enabled": True, "sensitivity": 0.35, "pretrained": ["hey_jarvis"], "model_paths": []})
SileroVad({"speech_threshold": 0.48})
sample = Path.home() / ".cache" / "openwhispr" / "parakeet-models" / "parakeet-tdt-0.6b-v3" / "test_wavs" / "en.wav"
if sample.exists():
    text = ParakeetSTT({"model_name": "nemo-parakeet-tdt-0.6b-v2", "quantization": "int8"}).transcribe(sample)
    print("Parakeet sample:", text)
tts = KokoroTTS({
    "model_path": "models/kokoro/kokoro-v1.0.onnx",
    "voices_path": "models/kokoro/voices-v1.0.bin",
    "voice": "af_heart",
    "speed": 1.0,
})
tts.synthesize_to_wav("Echo Node Windows audio test.", Path(os.environ["TEMP"]) / "echo-node-v2-windows-test.wav")
print("Checks complete")
'@
$CheckScript | & $VenvPython -

Write-Host
Write-Host "Windows install complete."
Write-Host "Run: .\.venv\Scripts\python.exe assistant_v2.py"
