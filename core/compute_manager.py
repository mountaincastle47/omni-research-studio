"""Hardware Acceleration & Compute Device Manager: CUDA, DirectML, and Multi-Core CPU Auto-Tuning."""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from core.i18n import get_text


@dataclass
class ComputeProfile:
    """Hardware profile and acceleration capabilities."""

    device_type: str  # "cuda", "directml", "cpu"
    display_name: str
    precision: str  # "float16", "float32", "int8"
    cpu_cores: int
    providers: List[str]
    gpu_name: str = ""
    details: str = ""


class ComputeManager:
    """Detects system compute hardware and provides optimized runtime configurations."""

    _instance: Optional[ComputeManager] = None
    _profile: Optional[ComputeProfile] = None

    def __init__(self) -> None:
        self._profile = self._detect_hardware()

    @classmethod
    def get_instance(cls) -> ComputeManager:
        if cls._instance is None:
            cls._instance = ComputeManager()
        return cls._instance

    @staticmethod
    def _detect_hardware() -> ComputeProfile:
        cpu_count = os.cpu_count() or 4
        detected_providers: List[str] = []

        # 1. Probe ONNX Runtime Providers
        try:
            import onnxruntime as ort
            detected_providers = ort.get_available_providers()
        except Exception:
            detected_providers = ["CPUExecutionProvider"]

        # 2. Check for CUDA via Torch or ONNX
        has_cuda = False
        gpu_name = ""
        try:
            import torch
            if torch.cuda.is_available():
                has_cuda = True
                try:
                    gpu_name = torch.cuda.get_device_name(0)
                except Exception:
                    gpu_name = "NVIDIA CUDA GPU"
        except Exception:
            pass

        if not has_cuda and "CUDAExecutionProvider" in detected_providers:
            has_cuda = True
            gpu_name = "NVIDIA CUDA (ONNX)"

        if has_cuda:
            return ComputeProfile(
                device_type="cuda",
                display_name="NVIDIA CUDA (FP16)",
                precision="float16",
                cpu_cores=cpu_count,
                providers=detected_providers,
                gpu_name=gpu_name or "NVIDIA CUDA",
                details=f"Hardware: {gpu_name} (FP16) | CPU Cores: {cpu_count}",
            )

        # 3. Check for DirectML (Windows GPU)
        if "DmlExecutionProvider" in detected_providers:
            return ComputeProfile(
                device_type="directml",
                display_name="DirectML GPU (FP32)",
                precision="float32",
                cpu_cores=cpu_count,
                providers=detected_providers,
                gpu_name="DirectML D3D12 Accelerator",
                details=f"Hardware: DirectML GPU Accelerator (FP32) | CPU Cores: {cpu_count}",
            )

        # 4. CPU Multi-Core Fallback (INT8)
        arch = platform.machine() or "x86_64"
        return ComputeProfile(
            device_type="cpu",
            display_name="CPU Multi-Core (INT8)",
            precision="int8",
            cpu_cores=cpu_count,
            providers=detected_providers or ["CPUExecutionProvider"],
            gpu_name="",
            details=f"Hardware: CPU Multi-Core ({cpu_count} threads, {arch}) | Quantization: INT8",
        )

    @property
    def profile(self) -> ComputeProfile:
        if self._profile is None:
            self._profile = self._detect_hardware()
        return self._profile

    def get_profile(self) -> ComputeProfile:
        """Return the current compute profile."""
        return self.profile

    def get_whisper_params(self, model_size: str = "tiny") -> Dict[str, Any]:
        """Generate optimized faster-whisper configuration for the detected hardware."""
        p = self.profile
        if p.device_type == "cuda":
            return {
                "device": "cuda",
                "compute_type": "float16",
                "device_index": 0,
            }
        else:
            return {
                "device": "cpu",
                "compute_type": "int8",
                "cpu_threads": min(p.cpu_cores, 8),
            }

    def get_rapidocr_params(self) -> Dict[str, Any]:
        """Generate optimized ONNX execution providers for RapidOCR."""
        p = self.profile
        providers: List[str] = []
        if p.device_type == "cuda" and "CUDAExecutionProvider" in p.providers:
            providers.append("CUDAExecutionProvider")
        elif p.device_type == "directml" and "DmlExecutionProvider" in p.providers:
            providers.append("DmlExecutionProvider")

        providers.append("CPUExecutionProvider")
        return {
            "providers": providers,
            "intra_op_num_threads": min(p.cpu_cores, 8),
        }

    def get_supported_providers(self) -> List[Dict[str, Any]]:
        """Return list of standard supported execution providers with host availability status."""
        detected = self.profile.providers
        return [
            {
                "id": "CPUExecutionProvider",
                "name": "CPU Multi-Core (INT8 Quantization)",
                "device_type": "cpu",
                "precision": "int8",
                "available": True,
            },
            {
                "id": "CUDAExecutionProvider",
                "name": "NVIDIA CUDA (FP16 Tensor Cores)",
                "device_type": "cuda",
                "precision": "float16",
                "available": "CUDAExecutionProvider" in detected,
            },
            {
                "id": "DmlExecutionProvider",
                "name": "DirectML (Windows D3D12 GPU FP32)",
                "device_type": "directml",
                "precision": "float32",
                "available": "DmlExecutionProvider" in detected,
            },
            {
                "id": "VulkanExecutionProvider",
                "name": "Vulkan Compute (Cross-Platform GPU FP32)",
                "device_type": "vulkan",
                "precision": "float32",
                "available": "VulkanExecutionProvider" in detected,
            },
        ]

    def set_provider(self, provider_id: str) -> ComputeProfile:
        """Switch active execution provider and update runtime profile."""
        cpu_count = os.cpu_count() or 4
        p = self.profile
        if provider_id == "CUDAExecutionProvider":
            self._profile = ComputeProfile(
                device_type="cuda",
                display_name="NVIDIA CUDA (FP16)",
                precision="float16",
                cpu_cores=cpu_count,
                providers=p.providers,
                gpu_name=p.gpu_name or "NVIDIA CUDA GPU",
                details=f"Hardware: {p.gpu_name or 'NVIDIA CUDA GPU'} (FP16) | CPU Cores: {cpu_count}",
            )
        elif provider_id == "DmlExecutionProvider":
            self._profile = ComputeProfile(
                device_type="directml",
                display_name="DirectML GPU (FP32)",
                precision="float32",
                cpu_cores=cpu_count,
                providers=p.providers,
                gpu_name=p.gpu_name or "DirectML D3D12 Accelerator",
                details=f"Hardware: DirectML GPU Accelerator (FP32) | CPU Cores: {cpu_count}",
            )
        elif provider_id == "VulkanExecutionProvider":
            self._profile = ComputeProfile(
                device_type="vulkan",
                display_name="Vulkan GPU (FP32)",
                precision="float32",
                cpu_cores=cpu_count,
                providers=p.providers,
                gpu_name="Vulkan Compute Surface",
                details=f"Hardware: Vulkan GPU Compute (FP32) | CPU Cores: {cpu_count}",
            )
        else:
            arch = platform.machine() or "x86_64"
            self._profile = ComputeProfile(
                device_type="cpu",
                display_name="CPU Multi-Core (INT8)",
                precision="int8",
                cpu_cores=cpu_count,
                providers=p.providers,
                gpu_name="",
                details=f"Hardware: CPU Multi-Core ({cpu_count} threads, {arch}) | Quantization: INT8",
            )
        return self._profile

    def get_badge_text(self, lang: str = "en") -> str:
        """Compact status bar badge text."""
        p = self.profile
        if p.device_type == "cuda":
            dev_text = get_text("compute_cuda", lang)
        elif p.device_type == "directml":
            dev_text = get_text("compute_dml", lang)
        elif p.device_type == "vulkan":
            dev_text = get_text("compute_vulkan", lang)
        else:
            dev_text = get_text("compute_cpu", lang)

        prefix = "⚡ Compute:" if lang == "en" else "⚡ 연산 가속:"
        return f"{prefix} {dev_text}"

    def get_tooltip_text(self, lang: str = "en") -> str:
        """Detailed hardware accelerator telemetry tooltip."""
        p = self.profile
        lines = [
            f"Compute Engine: {p.display_name}",
            f"Device Type: {p.device_type.upper()}",
            f"Arithmetic Precision: {p.precision.upper()}",
            f"Physical CPU Cores: {p.cpu_cores}",
        ]
        if p.gpu_name:
            lines.append(f"Accelerated Surface: {p.gpu_name}")
        if p.providers:
            lines.append(f"ONNX Providers: {', '.join(p.providers)}")
        return "\n".join(lines)
