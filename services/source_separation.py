"""Optional Demucs source-separation adapter for reference audio."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from importlib import util
from pathlib import Path

from core.audio_io import normalize_uploaded_audio

DEMUCS_UNAVAILABLE_WARNING = "Demucs 不可用，已跳过原唱人声分离。"


@dataclass
class SeparationResult:
    """Result from optional vocal/accompaniment separation."""

    vocals_path: str | None
    accompaniment_path: str | None
    backend: str
    available: bool
    warnings: list[str]
    separated: bool = False


def is_demucs_available() -> bool:
    """Return whether Demucs can be executed."""

    return util.find_spec("demucs") is not None


def separate_vocals(input_audio: str | Path, output_dir: str | Path, backend: str = "demucs") -> SeparationResult:
    """Backward-compatible source-separation entry point."""

    return separate_reference_audio(input_audio, output_dir, auto_separate_reference=True, backend=backend)


def separate_reference_audio(
    input_audio: str | Path,
    output_dir: str | Path,
    auto_separate_reference: bool = True,
    backend: str = "demucs",
) -> SeparationResult:
    """Try to split reference audio into vocals/accompaniment without failing the job."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if not auto_separate_reference:
        return SeparationResult(str(input_audio), None, backend, False, ["已关闭原唱人声分离。"], False)
    if backend != "demucs":
        return SeparationResult(str(input_audio), None, backend, False, [f"不支持的源分离后端：{backend}"], False)
    if not is_demucs_available():
        return SeparationResult(str(input_audio), None, backend, False, [DEMUCS_UNAVAILABLE_WARNING], False)

    demucs_out = output / "demucs"
    try:
        subprocess.run(
            [
                "python",
                "-m",
                "demucs",
                "--two-stems=vocals",
                "-o",
                str(demucs_out),
                str(input_audio),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception as exc:
        return SeparationResult(
            str(input_audio),
            None,
            backend,
            True,
            [f"Demucs 执行失败，已跳过原唱人声分离：{exc}"],
            False,
        )

    vocals, accompaniment = _find_demucs_outputs(demucs_out)
    if vocals is None:
        return SeparationResult(str(input_audio), None, backend, True, ["Demucs 未生成可用人声，已使用原唱音频作为参考。"], False)
    vocals_target = output / "reference_vocals.wav"
    accompaniment_target = output / "reference_accompaniment.wav"
    try:
        normalize_uploaded_audio(vocals, vocals_target)
        accompaniment_path = None
        if accompaniment is not None:
            normalize_uploaded_audio(accompaniment, accompaniment_target)
            accompaniment_path = str(accompaniment_target)
        return SeparationResult(str(vocals_target), accompaniment_path, backend, True, [], True)
    except Exception as exc:
        shutil.rmtree(demucs_out, ignore_errors=True)
        return SeparationResult(str(input_audio), None, backend, True, [f"Demucs 输出转换失败，已使用原唱音频作为参考：{exc}"], False)


def _find_demucs_outputs(root: Path) -> tuple[Path | None, Path | None]:
    vocals = None
    accompaniment = None
    for path in root.rglob("*.wav"):
        name = path.name.lower()
        if name == "vocals.wav":
            vocals = path
        elif name in {"no_vocals.wav", "accompaniment.wav"}:
            accompaniment = path
    return vocals, accompaniment
