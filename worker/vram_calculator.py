"""
VRAM Calculator for Echo-Node

Checks available GPU VRAM before loading models to prevent OOM crashes.
Supports NVIDIA (CUDA) via pynvml, with CPU fallback detection.
"""

import subprocess
import shutil
from typing import Optional, Tuple


class VRAMCalculator:
    """
    Calculate and monitor GPU VRAM availability.
    
    Supports NVIDIA GPUs via pynvml or nvidia-smi CLI.
    Provides CPU fallback detection for non-CUDA systems.
    """

    def __init__(self):
        """Initialize VRAM calculator."""
        self._nvml_available = False
        self._gpu_count = 0
        self._total_vram_mb = 0
        self._try_init_nvml()

    def _try_init_nvml(self) -> None:
        """Try to initialize NVIDIA NVML library."""
        try:
            import pynvml
            pynvml.nvmlInit()
            self._gpu_count = pynvml.nvmlDeviceGetCount()
            if self._gpu_count > 0:
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                self._total_vram_mb = info.total // (1024 * 1024)
                self._nvml_available = True
        except (ImportError, Exception):
            # NVML not available, try nvidia-smi CLI fallback
            self._detect_via_nvidia_smi()

    def _detect_via_nvidia_smi(self) -> None:
        """Detect VRAM using nvidia-smi CLI."""
        try:
            if not shutil.which('nvidia-smi'):
                return
            
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=memory.total', '--format=csv,nounits,noheader'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split('\n')
                if lines:
                    self._total_vram_mb = int(lines[0].strip())
                    self._gpu_count = len(lines)
        except (subprocess.TimeoutExpired, ValueError, Exception):
            pass

    def get_available_vram_mb(self) -> int:
        """
        Get currently available VRAM in MB.
        
        Returns:
            Available VRAM in MB, or 0 if no GPU detected
        """
        if not self._nvml_available:
            return 0
        
        try:
            import pynvml
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            return info.free // (1024 * 1024)
        except Exception:
            return 0

    def get_total_vram_mb(self) -> int:
        """
        Get total GPU VRAM in MB.
        
        Returns:
            Total VRAM in MB, or 0 if no GPU detected
        """
        return self._total_vram_mb

    def get_used_vram_mb(self) -> int:
        """
        Get currently used VRAM in MB.
        
        Returns:
            Used VRAM in MB, or 0 if no GPU detected
        """
        if not self._nvml_available:
            return 0
        
        try:
            import pynvml
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            return info.used // (1024 * 1024)
        except Exception:
            return 0

    def check_vram_requirement(self, required_mb: int, safety_margin_mb: int = 512) -> Tuple[bool, int, int]:
        """
        Check if VRAM requirement can be satisfied.
        
        Args:
            required_mb: VRAM needed in MB
            safety_margin_mb: Safety margin to reserve (default: 512MB)
        
        Returns:
            Tuple of (fits: bool, available_mb: int, recommended_action: str)
        """
        available = self.get_available_vram_mb()
        usable = available - safety_margin_mb
        
        if required_mb <= usable:
            return True, available, 0
        else:
            shortfall = required_mb - usable
            return False, available, shortfall

    def calculate_total_vram(self, providers: list) -> int:
        """
        Calculate total VRAM needed for a list of providers.
        
        Args:
            providers: List of provider instances with vram_requirement_mb property
        
        Returns:
            Total VRAM needed in MB
        """
        total = 0
        for provider in providers:
            if hasattr(provider, 'vram_requirement_mb'):
                total += provider.vram_requirement_mb
        return total

    def has_cuda(self) -> bool:
        """Check if CUDA GPU is available."""
        return self._gpu_count > 0

    def has_cpu_fallback(self) -> bool:
        """Check if CPU fallback is available (always true)."""
        return True

    def get_device_recommendation(self) -> str:
        """
        Get recommended device for inference.
        
        Returns:
            'cuda', 'openvino', or 'cpu'
        """
        if self.has_cuda():
            return 'cuda'
        
        # Check for Intel GPU (OpenVINO)
        try:
            result = subprocess.run(
                ['lspci'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if 'intel' in result.stdout.lower() and 'graphics' in result.stdout.lower():
                return 'openvino'
        except Exception:
            pass
        
        return 'cpu'

    def get_vram_report(self) -> dict:
        """
        Get full VRAM status report.
        
        Returns:
            Dict with total_mb, used_mb, available_mb, gpu_count
        """
        return {
            'total_mb': self._total_vram_mb,
            'used_mb': self.get_used_vram_mb(),
            'available_mb': self.get_available_vram_mb(),
            'gpu_count': self._gpu_count,
            'nvml_available': self._nvml_available,
        }

    def shutdown(self) -> None:
        """Cleanup NVML resources."""
        if self._nvml_available:
            try:
                import pynvml
                pynvml.nvmlShutdown()
            except Exception:
                pass
