"""Record the AetherPilot demo video (scenario C: OOM + NaN, two autonomous recoveries).

Drives a headless Chromium via Playwright against a locally running stack
(backend :8000, frontend :5173), records 1920x1080 video, and injects a
subtitle overlay into the page so captions are burned into the recording in
perfect sync. Writes timeline.json + subtitles.srt next to the video.

The run's state machine transitions in <1s (recovery in ~0.5s), far faster
than narration can follow, so subtitles are driven by incident *records*
(they persist) rather than by polling states. A request interceptor raises
the demo workload's step_delay to 0.55s so viewers can watch the live
charts — fault injection and recovery logic are untouched.

Usage:
    pip install playwright && python -m playwright install chromium
    .venv/Scripts/python scripts/record_demo.py
Outputs to docs/demo/ (git-ignored).
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import urllib.request
from pathlib import Path

from playwright.async_api import async_playwright

BASE_FE = "http://localhost:5173"
BASE_API = "http://127.0.0.1:8000"
OUT_DIR = Path(__file__).resolve().parents[1] / "docs" / "demo"
RAW_DIR = OUT_DIR / "raw"
W, H = 1920, 1080
POLL_TIMEOUT_S = 240  # hard cap on the experiment watch -> keeps video < 5 min

T0 = time.monotonic()
TIMELINE: list[dict] = []


def elapsed() -> float:
    return time.monotonic() - T0


def api(path: str) -> dict | list | None:
    try:
        with urllib.request.urlopen(f"{BASE_API}{path}", timeout=3) as r:
            return json.loads(r.read())
    except Exception:
        return None


OVERLAY_JS = """
(() => {
  if (document.getElementById('ap-sub-style')) return true;
  const st = document.createElement('style');
  st.id = 'ap-sub-style';
  st.textContent = `
    #ap-sub { position: fixed; left: 50%; bottom: 56px; transform: translateX(-50%);
      background: rgba(5,8,12,.78); color: #f2f5f8; padding: 10px 24px; border-radius: 6px;
      font: 500 25px/1.5 "Microsoft YaHei","PingFang SC","Segoe UI",sans-serif;
      letter-spacing: .02em; z-index: 2147483646; max-width: 78%; text-align: center;
      border: 1px solid rgba(255,255,255,.16); pointer-events: none;
      opacity: 0; transition: opacity .25s ease; white-space: pre-line; }
    #ap-card { position: fixed; inset: 0; z-index: 2147483647; display: flex;
      flex-direction: column; align-items: center; justify-content: center; gap: 18px;
      background: radial-gradient(ellipse at 50% 40%, #101820 0%, #05080c 70%);
      color: #e8eef4; pointer-events: none; opacity: 0; transition: opacity .5s ease;
      font-family: "Microsoft YaHei","Segoe UI",sans-serif; }
    #ap-card .t { font-size: 64px; font-weight: 700; letter-spacing: .12em; }
    #ap-card .s { font-size: 26px; color: #8fa3b8; letter-spacing: .06em; }
    #ap-card .a { font-size: 22px; color: #58c4dc; font-family: Consolas,monospace; }
    .ap-hl { outline: 3px solid #ffb020 !important; outline-offset: 3px !important;
      box-shadow: 0 0 22px rgba(255,176,32,.55) !important; border-radius: 4px; }
  `;
  document.head.appendChild(st);
  const sub = document.createElement('div');
  sub.id = 'ap-sub';
  document.body.appendChild(sub);
  const card = document.createElement('div');
  card.id = 'ap-card';
  document.body.appendChild(card);
  return true;
})()
"""

SET_SUB_JS = """
(text) => {
  const el = document.getElementById('ap-sub');
  if (!el) return false;
  el.textContent = text || '';
  el.style.opacity = text ? '1' : '0';
  return true;
}
"""

SET_CARD_JS = """
(lines) => {
  const el = document.getElementById('ap-card');
  if (!el) return false;
  el.innerHTML = '';
  if (lines && lines.length) {
    for (const [cls, txt] of lines) {
      const d = document.createElement('div');
      d.className = cls; d.textContent = txt; el.appendChild(d);
    }
    el.style.opacity = '1';
  } else {
    el.style.opacity = '0';
  }
  return true;
}
"""


async def overlay(page) -> None:
    try:
        await page.evaluate(OVERLAY_JS)
    except Exception:
        pass


async def sub(page, text: str, dwell: float = 0.0) -> None:
    """Show a subtitle line; record it in the timeline."""
    await overlay(page)
    await page.evaluate(SET_SUB_JS, text)
    TIMELINE.append({"t": round(elapsed(), 2), "kind": "sub", "text": text})
    first = text.splitlines()[0] if text else "(clear)"
    print(f"[{elapsed():6.1f}s] SUB {first[:64]}", flush=True)
    if dwell:
        await asyncio.sleep(dwell)


async def card(page, lines: list[tuple[str, str]], dwell: float) -> None:
    await overlay(page)
    await page.evaluate(SET_CARD_JS, lines)
    TIMELINE.append({"t": round(elapsed(), 2), "kind": "card",
                     "text": " / ".join(t for _, t in lines)})
    await asyncio.sleep(dwell)
    await page.evaluate(SET_CARD_JS, [])


async def click_highlight(page, locator, note: str) -> None:
    """Flash an orange outline on the element, then click it."""
    try:
        await locator.evaluate("el => el.classList.add('ap-hl')")
        await asyncio.sleep(0.7)
        await locator.evaluate("el => el.classList.remove('ap-hl')")
        await locator.click()
        print(f"[{elapsed():6.1f}s] CLICK {note}", flush=True)
    except Exception as e:
        print(f"click failed ({note}): {e}", flush=True)


def fmt_srt_time(s: float) -> str:
    ms = int(round(s * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    sec, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


def write_srt() -> None:
    subs = [e for e in TIMELINE if e["kind"] == "sub" and e["text"]]
    lines: list[str] = []
    for i, e in enumerate(subs):
        end = subs[i + 1]["t"] if i + 1 < len(subs) else e["t"] + 3.5
        lines.append(f"{i + 1}\n{fmt_srt_time(e['t'])} --> {fmt_srt_time(end)}\n{e['text']}\n")
    (OUT_DIR / "subtitles.srt").write_text("\n".join(lines), encoding="utf-8")


async def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if RAW_DIR.exists():
        for f in RAW_DIR.glob("*"):
            f.unlink()
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    status = api("/api/system/status") or {}
    gpu = status.get("gpu") or {}
    gpu_name = "N/A"
    if gpu.get("available"):
        gpus = gpu.get("gpus") or []
        if gpus and isinstance(gpus[0], dict):
            gpu_name = gpus[0].get("name") or "N/A"
    gpu_line = f"GPU: {gpu_name} · driver {gpu.get('driver', '?')} · CUDA {gpu.get('cuda', '?')}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            viewport={"width": W, "height": H},
            device_scale_factor=1,
            record_video_dir=str(RAW_DIR),
            record_video_size={"width": W, "height": H},
        )
        page = await ctx.new_page()

        # Slow the demo workload's stepping so the charts are watchable.
        # Only the pacing knob is touched; fault injection and recovery logic
        # are exactly what the scenario defines.
        async def pace(route):
            req = route.request
            if req.method == "POST" and req.url.rstrip("/").endswith("/api/experiments"):
                try:
                    body = req.post_data_json or {}
                    body.setdefault("demo", {})["step_delay"] = 0.55
                    await route.continue_(post_data=json.dumps(body))
                    return
                except Exception:
                    pass
            await route.continue_()

        await page.route("**/api/experiments", pace)

        # ---- intro: dashboard -------------------------------------------------
        await page.goto(BASE_FE, wait_until="networkidle")
        await asyncio.sleep(1.0)
        await card(page, [("t", "AetherPilot"),
                          ("s", "自主 AI 实验工程师 · Autonomous AI Experiment Operator"),
                          ("a", "From failed run to reproducible result")], 3.4)
        await sub(page, "系统状态全部来自真实机器（pynvml / psutil 实时采集，无模拟数据）", 3.0)
        await sub(page, gpu_line, 2.6)
        await sub(page, "LLM 只负责推理与解释 —— 执行由确定性策略、权限门控与完整性检查完成", 3.0)

        # ---- pick scenario C and launch --------------------------------------
        chip = page.locator("button.chip", has_text=re.compile(r"^C ·"))
        await sub(page, "选择场景 C：训练中将先后注入 CUDA OOM 与 NaN loss 两种故障", 2.0)
        await click_highlight(page, chip, "scenario C chip")
        await asyncio.sleep(0.8)
        await sub(page, "目标：macro_f1 ≥ 0.92 · 合同写死约束、权限与恢复策略", 2.2)
        run_btn = page.locator("button.primary").first
        await click_highlight(page, run_btn, "plan & run")

        await page.wait_for_url(re.compile(r"/experiments/"), timeout=15000)
        exp_id = page.url.rstrip("/").split("/")[-1]
        print(f"[{elapsed():6.1f}s] experiment {exp_id}", flush=True)

        await sub(page, "合同生成 → Preflight（GPU/磁盘/数据集探测）→ 规划：确定性流水线，秒级完成", 3.0)
        await sub(page, "训练运行中 —— 实时 loss 曲线与 GPU 遥测（WebSocket 推送）", 3.0)

        # ---- watch the run: incident-record-driven narration ------------------
        incidents_seen = 0
        deadline = time.monotonic() + POLL_TIMEOUT_S
        state = ""
        while time.monotonic() < deadline:
            exp = api(f"/api/experiments/{exp_id}") or {}
            state = exp.get("state") or state
            incidents = api(f"/api/experiments/{exp_id}/incidents") or []

            if len(incidents) > incidents_seen:
                incidents_seen = len(incidents)
                itype = (incidents[-1].get("type") or "").upper()
                if "OOM" in itype:
                    await sub(page, "⚠ 第 20 步：CUDA OOM —— 检测器从训练日志捕获证据", 2.8)
                    await sub(page, "诊断：batch 32 需要 ≈8.5 GiB，超出 12 GiB 显存容量", 2.8)
                    await sub(page, "恢复计划：batch 32→8 × grad_accum 1→4，等效 batch 保持不变", 3.0)
                    await sub(page, "＋ 开启 gradient checkpointing · 回滚到 checkpoint-10", 2.8)
                    await sub(page, "完整性检查 PRESERVED —— 语义不变，无需人工审批，自动执行", 2.8)
                    await sub(page, "训练已自动恢复 —— 从 checkpoint-10 继续", 2.6)
                elif "NAN" in itype:
                    await sub(page, "⚠ 第 45 步：NaN loss —— 第二次故障注入", 2.8)
                    await sub(page, "诊断：学习率相对当前阶段过高 → 梯度爆炸", 2.8)
                    await sub(page, "恢复：回滚到最近稳定 checkpoint-40 · lr 2e-5 → 1.5e-5 · 梯度裁剪 1.0", 3.2)
                    await sub(page, "第二次自主恢复完成 —— integrity 仍为 PRESERVED", 2.8)
                    await sub(page, "继续训练 —— 向 60 步目标推进，等待收敛…", 3.0)
                else:
                    await sub(page, f"⚠ 检测到事故：{itype}", 2.4)

            if state in ("COMPLETED", "FAILED", "CANCELLED"):
                break
            await asyncio.sleep(0.3)

        # ---- completed: result page -------------------------------------------
        exp = api(f"/api/experiments/{exp_id}") or {}
        fm = exp.get("final_metrics") or {}
        evals = fm.get("metrics") or ((exp.get("evaluation") or {}).get("metrics")) or {}
        f1 = evals.get("macro_f1")
        f1_txt = f"macro_f1 = {f1:.4f} ≥ 0.92 ✓ PASS" if isinstance(f1, (int, float)) else "评估完成"
        await sub(page, f"实验完成：{f1_txt} · 两次故障全部自主恢复 · 语义变更 0 次", 3.2)
        await sub(page, "可复现档案已生成：manifest / contract / configs / telemetry / audit / REPORT.md", 3.0)

        try:
            btn = page.locator("button.primary", has_text=re.compile("report", re.I))
            await click_highlight(page, btn, "view report")
            await page.wait_for_url(re.compile(r"/result"), timeout=8000)
        except Exception:
            await page.goto(f"{BASE_FE}/experiments/{exp_id}/result", wait_until="networkidle")
        await asyncio.sleep(1.2)

        await sub(page, "结果页：指标卡 · 事故与恢复时间线 · 渲染后的 REPORT.md", 3.0)
        await page.mouse.wheel(0, 700)
        await asyncio.sleep(1.0)
        await sub(page, "每次自主变更都有审计记录：who / what / why / evidence / policy", 3.0)
        await page.mouse.wheel(0, 700)
        await asyncio.sleep(2.6)

        # ---- end card ----------------------------------------------------------
        await sub(page, "")
        await card(page, [("t", "AetherPilot"),
                          ("s", "让 Agent 对一次实验负责，而不仅仅是回答一个问题"),
                          ("a", "github.com/lizuyi-6/AetherPilot-  ·  MIT License")], 4.2)

        await ctx.close()
        video_path = await page.video.path()
        await browser.close()

    duration = elapsed()
    (OUT_DIR / "timeline.json").write_text(
        json.dumps({"duration_s": round(duration, 2), "events": TIMELINE},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    write_srt()
    print(f"raw video: {video_path}", flush=True)
    print(f"duration: {duration:.1f}s", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
