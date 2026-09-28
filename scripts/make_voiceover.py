"""Generate the demo-video voiceover with StepFun stepaudio-2.5-tts and mix it in.

Pipeline:
  1. synthesize one wav per narration block (step_plan endpoint, voice=boyinnansheng)
  2. probe durations; if a block exceeds its on-screen window, atempo it slightly
     (<= 1.15x, imperceptible) instead of letting speech overlap the next section
  3. assemble a full-length track with adelay at each block's timestamp
  4. mux into the video; the final title card is extended with ~2.5s of cloned
     frames so the last line finishes before the video ends

Usage:
    set AETHER_STEP_API_KEY=...   # StepFun API key (step_plan tier)
    .venv/Scripts/python scripts/make_voiceover.py
Outputs docs/demo/voiceover.wav and docs/demo/aetherpilot-demo-voiced.mp4.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

API = "https://api.stepfun.com/step_plan/v1/audio/speech"
KEY = os.environ.get("AETHER_STEP_API_KEY", "")
MODEL = "stepaudio-2.5-tts"
VOICE = "boyinnansheng"
INSTRUCTION = "沉稳专业的技术演示旁白，吐字清晰，语速适中，句间自然停顿"

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "docs" / "demo"
TMP = DEMO / "vo_tmp"

# (start_s, text) — starts match the burned-in subtitle timeline in timeline.json
SEGMENTS: list[tuple[float, str]] = [
    (4.6, "AetherPilot——自主 AI 实验工程师。"),
    (7.9, "系统状态全部来自真实机器。LLM 只做推理，执行交给确定性的策略和权限门控。"),
    (16.4, "选择场景 C，注入两种故障。目标 macro F1 不低于零点九二。"),
    (23.9, "合同生成、环境探测、规划，全部在一秒内完成。训练启动——实时曲线与 GPU 遥测同步推送。"),
    (35.3, "第二十步，CUDA 显存溢出。诊断：batch 32 需要八点五 GB，超出十二 GB 容量。"
           "恢复计划：batch 降到 8，梯度累积提到 4，等效 batch 保持不变。"
           "完整性检查通过，自动执行，训练恢复。"),
    (55.2, "第四十五步，NaN loss，第二次故障。学习率过高导致梯度爆炸。"
           "回滚到最近的稳定检查点，学习率下调，加梯度裁剪。第二次自主恢复完成，完整性保持。"),
    (70.2, "实验完成：macro F1 达到零点九三二三，达标。两次故障全部自主恢复。"),
    (78.5, "结果页包含指标、事故时间线和完整报告，每次自主变更都有审计记录。"),
    (88.2, "AetherPilot，让 Agent 对实验负责。"),
]

TAIL_PAD_S = 2.5  # cloned end-card frames so the closing line finishes


def synth(text: str, out: Path) -> None:
    body = json.dumps({
        "model": MODEL, "voice": VOICE, "input": text,
        "instruction": INSTRUCTION, "response_format": "wav",
    }).encode()
    req = urllib.request.Request(API, data=body, headers={
        "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        out.write_bytes(r.read())


def probe(p: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(p)],
        capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def main() -> None:
    TMP.mkdir(parents=True, exist_ok=True)
    raw, fixed = [], []
    for i, (t, text) in enumerate(SEGMENTS):
        f = TMP / f"seg{i:02d}.wav"
        for attempt in range(3):
            try:
                synth(text, f)
                break
            except Exception as e:
                print(f"seg{i} attempt {attempt + 1} failed: {e}", flush=True)
                time.sleep(3 * (attempt + 1))
        else:
            raise SystemExit(f"segment {i} failed after retries")
        d = probe(f)
        raw.append((t, d, text))
        print(f"seg{i:02d} @{t:6.1f}s  {d:5.2f}s  {text[:28]}", flush=True)
        time.sleep(1)

    # speed-fit: never let a block run into the next one by more than 0.4s
    for i, (t, d, _text) in enumerate(raw):
        window = (raw[i + 1][0] if i + 1 < len(raw) else 88.2) - t
        slack = window - 0.4 if i + 1 < len(raw) else TAIL_PAD_S + (90.64 - t)
        if d > slack:
            tempo = min(1.15, d / slack)
            src, dst = TMP / f"seg{i:02d}.wav", TMP / f"seg{i:02d}f.wav"
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
                 "-filter:a", f"atempo={tempo:.3f}", str(dst)], check=True)
            nd = probe(dst)
            print(f"seg{i:02d} atempo x{tempo:.3f}: {d:.2f}s -> {nd:.2f}s "
                  f"(window {window:.1f}s)", flush=True)
            fixed.append(dst)
        else:
            fixed.append(TMP / f"seg{i:02d}.wav")

    # assemble: each segment delayed to its timestamp over silence
    inputs, filters = [], []
    total = 90.64 + TAIL_PAD_S
    for i, (t, _d, _text) in enumerate(raw):
        inputs += ["-i", str(fixed[i])]
        filters.append(f"[{i}:a]adelay={int(t * 1000)}|{int(t * 1000)}[s{i}]")
    mix = "".join(f"[s{i}]" for i in range(len(raw)))
    filters.append(f"{mix}amix=inputs={len(raw)}:normalize=0,"
                   f"apad=whole_dur={total},loudnorm=I=-17:TP=-1.5[a]")
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", *inputs,
         "-filter_complex", ";".join(filters), "-map", "[a]",
         "-t", f"{total}", "-ar", "44100", str(DEMO / "voiceover.wav")], check=True)
    print(f"voiceover.wav: {probe(DEMO / 'voiceover.wav'):.2f}s", flush=True)

    # mux into the video, padding the tail with cloned end-card frames
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-i", str(DEMO / "aetherpilot-demo.mp4"), "-i", str(DEMO / "voiceover.wav"),
         "-filter_complex",
         f"[0:v]tpad=stop_mode=clone:stop_duration={TAIL_PAD_S}[v]",
         "-map", "[v]", "-map", "1:a",
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest",
         str(DEMO / "aetherpilot-demo-voiced.mp4")], check=True)
    print(f"final: {probe(DEMO / 'aetherpilot-demo-voiced.mp4'):.2f}s", flush=True)


if __name__ == "__main__":
    main()
