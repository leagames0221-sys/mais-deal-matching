"""MAIS Deal Matching demo 動画 全自動制作 pipeline (action-then-narration timing model)。

4 段 orchestrator:
  1. AivisSpeech HTTP API (Style-Bert-VITS2、 まお おちついた speaker_id=888753763) で 14 scene raw narration WAV 生成
  2. Playwright (Chromium、 1920x1080) で uvicorn live demo flow を navigate + WebM 録画 + 各 scene action_elapsed 計測
  3. action_elapsed + settle buffer を lead-in silence にして per-scene padded WAV build (narration が settled page 上で 流れる timing 保証)
  4. ffmpeg で WebM + narration WAV → MP4 最終合成 (SRT 字幕 burn-in + 末尾 credit overlay + tpad で video 末尾 frame clone)

precondition (起動済 / install 済 verify):
  - uvicorn http://127.0.0.1:8001/health = 200
  - AivisSpeech engine http://127.0.0.1:10101/version = 200
    起動: `.vendor/aivis-engine/Windows-x64/run.exe --host 127.0.0.1 --port 10101`
  - ffmpeg (PATH 上、 `winget install Gyan.FFmpeg`)
  - playwright + chromium (`pip install -r requirements-video.txt && playwright install chromium`)

run:
  PYTHONIOENCODING=utf-8 python -m scripts.produce_video
  → out_video/mais_deal_matching_demo.mp4 (約 80 秒、 1080p、 約 6-7 MB)

env var (override 可):
  SPEAKER_ID=<int>     default 888753763 (まお おちついた)
  PITCH_SCALE=<float>  default 0.0、 ±0.03 が natural 域 (Style-Bert-VITS2 model 制限)
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests

# ─── config ───────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "out_video"
TEMP_DIR = OUTPUT_DIR / "_temp"
UVICORN_URL = "http://127.0.0.1:8001"
ENGINE_URL = "http://127.0.0.1:10101"  # AivisSpeech-Engine standalone
SPEAKER_ID = int(os.environ.get("SPEAKER_ID", "888753763"))  # まお おちついた (cross-PJ 統一)

LEAD_IN_SEC = 0.4   # legacy (--narration-only mode の fallback)
TRAIL_OUT_SEC = 0.4  # narration 終了から次 scene までの最低 silence
SETTLE_BUFFER_SEC = 0.3  # action 完了 (networkidle) 後 narration 開始 までの buffer (画面 settle 確保)

# pitchScale: AivisSpeech (Style-Bert-VITS2) は ±0.03 が natural 域、 超過で音割れ artifact
PITCH_SCALE = float(os.environ.get("PITCH_SCALE", "0.0"))

VIEWPORT = {"width": 1920, "height": 1080}


# ─── scene definitions (id, duration_sec, action, narration_text) ────

@dataclass
class Scene:
    id: str
    duration: float
    action: Callable
    narration: str


def _scenes_factory() -> list[Scene]:
    """Playwright page を受け取り navigation を行う lambda 群を構築。"""
    def s1(p):
        p.goto(f"{UVICORN_URL}/")
        p.wait_for_load_state("networkidle")

    def s2(p):
        p.evaluate("window.scrollTo({top: 800, behavior: 'smooth'})")

    def s3(p):
        p.evaluate("window.scrollTo({top: 1600, behavior: 'smooth'})")

    def s4(p):
        p.evaluate("document.getElementById('demo-profile').scrollIntoView({behavior:'smooth', block:'start'})")

    def s5(p):
        # 後継候補 mock-signin (合成 sample 先頭 = PROF-000001)
        p.locator("#demo-profile form button").first.click()
        p.wait_for_url("**/mypage")
        p.wait_for_load_state("networkidle")

    def s6(p):
        p.locator("a:has-text('個人情報を一時的に閲覧')").click()
        p.wait_for_load_state("networkidle")

    def s7(p):
        p.locator("nav a:has-text('マッチング')").first.click()
        p.wait_for_url("**/match")
        p.wait_for_load_state("networkidle")

    def s8(p):
        # 紹介リクエスト click は heavy POST (Vault encrypt + DB save)、 timeout 90s
        p.locator("button:has-text('紹介をリクエスト')").first.click(timeout=90000)
        p.wait_for_load_state("networkidle", timeout=60000)

    def s9(p):
        p.locator("nav a:has-text('監査ログ')").click()
        p.wait_for_url("**/audit-log")
        p.wait_for_load_state("networkidle")

    def s10(p):
        # signout → landing → 企業 sample へ scroll → 企業 signin
        p.locator("nav form button:has-text('ログアウト')").click()
        p.wait_for_url(f"{UVICORN_URL}/")
        p.wait_for_load_state("networkidle")
        p.evaluate("document.getElementById('demo-company').scrollIntoView({behavior:'smooth', block:'start'})")
        p.wait_for_timeout(700)  # scroll 完了待ち
        p.locator("#demo-company form button").first.click()
        p.wait_for_url("**/company/mypage")
        p.wait_for_load_state("networkidle")

    def s11(p):
        p.locator("nav a:has-text('候補者マッチング')").click()
        p.wait_for_url("**/company/match")
        p.wait_for_load_state("networkidle")

    def s12(p):
        # 紹介リクエスト click (企業側、 同じく heavy POST timeout 90s)
        p.locator("button:has-text('紹介をリクエスト')").first.click(timeout=90000)
        p.wait_for_load_state("networkidle", timeout=60000)

    def s13(p):
        p.locator("nav a:has-text('監査ログ')").click()
        p.wait_for_url("**/audit-log")
        p.wait_for_load_state("networkidle")

    def s14(p):
        # closing: landing 戻り
        p.locator("nav form button:has-text('ログアウト')").click()
        p.wait_for_url(f"{UVICORN_URL}/")
        p.wait_for_load_state("networkidle")
        p.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")

    return [
        # narration text: 単語間空白除去 + 句読点削減 (2026-05-13、 cross-PJ writing rule、 SSoT § 3)
        # duration は auto-sync logic が actual WAV + margin に literal 上書き、 初期値は低め可
        Scene("S1", 5.0, s1, "マイスディールマッチング。事業承継マッチングのエーアイです。"),
        Scene("S2", 5.5, s2, "5段階ハイブリッド検索と、ボルトパターンが特徴です。"),
        Scene("S3", 5.0, s3, "個人情報保護法26-2条の暗号化要件にも適合しています。"),
        Scene("S4", 4.5, s4, "後継候補としてログインします。"),
        Scene("S5", 5.5, s5, "公開情報のみがマイページに表示されます。"),
        Scene("S6", 6.5, s6, "氏名や連絡先は、暗号化された保管庫に隔離されています。"),
        Scene("S7", 7.5, s7, "マッチする企業上位5社を、該当理由付きで提示します。"),
        Scene("S8", 6.5, s8, "紹介リクエストで、企業の個人情報が表示されます。"),
        Scene("S9", 5.5, s9, "全アクセスは改ざん不能な監査ログに残ります。"),
        Scene("S10", 5.5, s10, "次に、企業としてログインします。"),
        Scene("S11", 6.5, s11, "貴社にマッチする候補者5名を提示します。"),
        Scene("S12", 6.5, s12, "候補者の個人情報も、同じ仕組みで表示されます。"),
        Scene("S13", 5.5, s13, "両側の全アクセスがログに記録されます。"),
        Scene("S14", 4.5, s14, "全機能、合成データで動作確認済みです。"),
    ]


SCENES = _scenes_factory()


# ─── helpers ──────────────────────────────────────────────────────────

def info(msg: str) -> None:
    print(f"[produce_video] {msg}", flush=True)


def check_preconditions() -> None:
    """uvicorn / AivisSpeech / ffmpeg / playwright + chromium の起動確認。"""
    errors = []

    try:
        r = requests.get(f"{UVICORN_URL}/health", timeout=3)
        assert r.status_code == 200
        info(f"OK uvicorn live ({UVICORN_URL}/health = 200)")
    except Exception as e:
        errors.append(f"uvicorn 起動不能: {UVICORN_URL} ({e}). 別 shell で uvicorn を起動してください")

    try:
        r = requests.get(f"{ENGINE_URL}/version", timeout=3)
        assert r.status_code == 200
        info(f"OK AivisSpeech engine live ({ENGINE_URL}/version = {r.text.strip()})")
    except Exception as e:
        hint = ".vendor/aivis-engine/Windows-x64/run.exe --host 127.0.0.1 --port 10101 で起動してください"
        errors.append(f"AivisSpeech engine 起動不能: {ENGINE_URL} ({e}). {hint}")

    if shutil.which("ffmpeg") is None:
        errors.append("ffmpeg が PATH に不在。 `winget install Gyan.FFmpeg` で install してください")
    else:
        info(f"OK ffmpeg ({shutil.which('ffmpeg')})")

    try:
        from playwright.sync_api import sync_playwright  # noqa
        info("OK playwright (Python binding)")
    except ImportError:
        errors.append("playwright 未 install。 `pip install -r requirements-video.txt` を実行してください")

    if errors:
        info("==== precondition error ====")
        for e in errors:
            info(f"  - {e}")
        sys.exit(1)


def aivis_synthesize(text: str) -> bytes:
    """AivisSpeech HTTP API で WAV bytes 生成 (Style-Bert-VITS2、 素 AI prosody)。"""
    q = requests.post(
        f"{ENGINE_URL}/audio_query",
        params={"text": text, "speaker": SPEAKER_ID},
        timeout=15,
    )
    q.raise_for_status()
    q_json = q.json()
    if PITCH_SCALE != 0.0:
        q_json["pitchScale"] = PITCH_SCALE
    s = requests.post(
        f"{ENGINE_URL}/synthesis",
        params={"speaker": SPEAKER_ID},
        json=q_json,
        timeout=60,
    )
    s.raise_for_status()
    return s.content


def ffprobe_duration(path: Path) -> float:
    """ffprobe で WAV/WebM の長さ秒を取得。"""
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)]
    )
    return float(out.decode().strip())


def make_padded_wav(scene: Scene, raw_wav_path: Path, out_path: Path, lead_in_sec: float | None = None) -> None:
    """raw WAV を scene.duration に合わせて lead-in + trail-out silence で sandwich pad。

    lead_in_sec が None なら legacy LEAD_IN_SEC (0.4s) を使用 (--narration-only mode 等)。
    full pipeline では action_elapsed + SETTLE_BUFFER_SEC を渡して action-then-narration 同期する。
    """
    lead = LEAD_IN_SEC if lead_in_sec is None else lead_in_sec
    raw_dur = ffprobe_duration(raw_wav_path)
    if raw_dur > scene.duration - lead - TRAIL_OUT_SEC:
        info(f"  WARN [{scene.id}] narration {raw_dur:.2f}s が scene {scene.duration:.1f}s (lead={lead:.2f}s) に対し tight、 trail_out 縮小")

    # adelay で先頭 silence、 apad で末尾 silence を scene.duration まで延長
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(raw_wav_path),
            "-af", f"adelay={int(lead * 1000)}|{int(lead * 1000)},apad=whole_dur={scene.duration}",
            "-ar", "24000", "-ac", "1",
            str(out_path),
        ],
        check=True,
    )


def concat_narration(scene_padded_wavs: list[Path], out_path: Path) -> None:
    """全 scene padded WAV を concat demuxer で 1 本に結合。"""
    concat_list = TEMP_DIR / "concat_audio.txt"
    concat_list.write_text(
        "\n".join(f"file '{p.as_posix()}'" for p in scene_padded_wavs),
        encoding="utf-8",
    )
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c", "copy",
            str(out_path),
        ],
        check=True,
    )


def record_demo() -> Path:
    """Playwright で action-then-narration model で demo flow 録画、 WebM path 返却。

    各 scene で:
      1. action() 実行 (page.goto / click / scroll 等)
      2. wait_for_load_state('networkidle') で画面 settle 完了 待ち
      3. scene.action_elapsed = wall-clock 計測値 (settled 状態到達まで)
      4. narration_window = raw_duration + SETTLE_BUFFER_SEC + TRAIL_OUT_SEC を wait
         → narration は settled page 上で 流れる
      5. 次 scene へ

    結果: video timeline = audio timeline (action_lead + narration_window per scene) が 1:1 一致、
          narration が 該当 page 上で 流れる (timing drift 構造的解消)。
    """
    from playwright.sync_api import sync_playwright

    info("Playwright Chromium 起動中... (action-then-narration timing mode)")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--hide-scrollbars"],
        )
        context = browser.new_context(
            viewport=VIEWPORT,
            record_video_dir=str(TEMP_DIR),
            record_video_size=VIEWPORT,
        )
        page = context.new_page()

        for scene in SCENES:
            raw_dur = getattr(scene, "raw_duration", 0.0)
            info(f"  [{scene.id}] action: {scene.narration[:30]}... (narration_raw={raw_dur:.2f}s)")
            t0 = time.time()
            scene.action(page)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                # networkidle timeout (e.g., long-poll endpoints) → 既に動作可な state、 続行
                pass
            scene.action_elapsed = time.time() - t0
            narration_window_sec = raw_dur + SETTLE_BUFFER_SEC + TRAIL_OUT_SEC
            info(f"    action_elapsed={scene.action_elapsed:.2f}s, narration_window={narration_window_sec:.2f}s")
            page.wait_for_timeout(int(narration_window_sec * 1000))

        context.close()  # video flush
        browser.close()

    webms = sorted(TEMP_DIR.glob("*.webm"), key=lambda p: p.stat().st_mtime)
    if not webms:
        raise RuntimeError(f"WebM が {TEMP_DIR} に生成されなかった")
    return webms[-1]


def _fmt_srt_time(t: float) -> str:
    """SRT timestamp 形式 (HH:MM:SS,mmm)。"""
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t - h * 3600 - m * 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def generate_srt(out_path: Path) -> None:
    """14 scene narration を SRT 形式に literal 出力。

    action-then-narration model で scene.action_elapsed が set 済の場合:
      lead = action_elapsed + SETTLE_BUFFER_SEC で start time 計算
    set されてない場合 (--narration-only mode):
      legacy LEAD_IN_SEC で計算
    """
    lines: list[str] = []
    cum = 0.0
    for i, scene in enumerate(SCENES, 1):
        action_elapsed = getattr(scene, "action_elapsed", None)
        lead = (action_elapsed + SETTLE_BUFFER_SEC) if action_elapsed is not None else LEAD_IN_SEC
        start = cum + lead
        end = cum + scene.duration - TRAIL_OUT_SEC
        cum += scene.duration
        lines.append(f"{i}\n{_fmt_srt_time(start)} --> {_fmt_srt_time(end)}\n{scene.narration}\n")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def compose_final(webm: Path, narration: Path, out_mp4: Path) -> None:
    """WebM + narration WAV → MP4 (1080p / H.264 / AAC) + 字幕 burn-in + 末尾クレジット overlay。"""
    credit_path = TEMP_DIR / "credit.txt"
    credit_path.write_text(
        "MAIS Deal Matching (PoC) / AivisSpeech: まお おちついた / 合成データ only",
        encoding="utf-8",
    )

    srt_path = TEMP_DIR / "narration.srt"
    generate_srt(srt_path)

    fontfile_escaped = "C\\:/Windows/Fonts/YuGothM.ttc"
    textfile_escaped = credit_path.as_posix().replace(":", "\\:")
    srt_escaped = srt_path.as_posix().replace(":", "\\:")

    narration_dur = ffprobe_duration(narration)
    video_dur = ffprobe_duration(webm)
    enable_from = max(0.0, narration_dur - 7.0)

    # tpad: video が narration より短い場合 (Playwright WebM 末尾 frame drop 等) 最終 frame を clone で extend。
    # action-then-narration model で audio = action_lead + raw + trail per scene 累積 = 全 narration が
    # cut なし re-play されるための video 長さ保証。
    pad_sec = max(0.0, narration_dur - video_dur + 0.2)  # +0.2s buffer
    tpad_filter = f"tpad=stop_mode=clone:stop_duration={pad_sec:.2f}" if pad_sec > 0.01 else None

    subtitles_filter = (
        f"subtitles='{srt_escaped}':"
        "force_style='FontName=Yu Gothic UI Semibold,"
        "Fontsize=22,PrimaryColour=&HFFFFFF&,OutlineColour=&H000000&,"
        "BackColour=&H80000000&,BorderStyle=1,Outline=2,Shadow=1,"
        "MarginV=30,Alignment=2'"
    )

    drawtext_filter = (
        f"drawtext=fontfile='{fontfile_escaped}':"
        f"textfile='{textfile_escaped}':"
        "fontcolor=white:fontsize=26:"
        "x=(w-text_w)/2:y=h-th-40:"
        "box=1:boxcolor=black@0.75:boxborderw=14:"
        f"enable='gte(t,{enable_from:.2f})'"
    )

    vf_parts = [f for f in (tpad_filter, subtitles_filter, drawtext_filter) if f]
    vf_chain = ",".join(vf_parts)
    if tpad_filter:
        info(f"  tpad: video {video_dur:.2f}s → narration {narration_dur:.2f}s (clone {pad_sec:.2f}s 末尾 frame)")

    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(webm),
            "-i", str(narration),
            "-vf", vf_chain,
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest",
            "-metadata", f"comment=AivisSpeech:speaker_id={SPEAKER_ID} / MAIS Deal Matching PoC / synthetic data only",
            str(out_mp4),
        ],
        check=True,
    )


# ─── main orchestrator ───────────────────────────────────────────────

def main() -> int:
    narration_only = "--narration-only" in sys.argv
    info("=== MAIS Deal Matching demo video pipeline (action-then-narration model) ===")
    if narration_only:
        info("(--narration-only mode: AivisSpeech synthesis のみ実行、 Playwright + ffmpeg compose skip)")
    OUTPUT_DIR.mkdir(exist_ok=True)
    TEMP_DIR.mkdir(exist_ok=True)

    info("\n[0/3] precondition check")
    if narration_only:
        try:
            r = requests.get(f"{ENGINE_URL}/version", timeout=3)
            assert r.status_code == 200
            info(f"OK AivisSpeech engine live ({ENGINE_URL}/version = {r.text.strip()})")
        except Exception as e:
            info(f"AivisSpeech engine 起動不能: {ENGINE_URL} ({e})")
            sys.exit(1)
        if shutil.which("ffmpeg") is None:
            info("ffmpeg が PATH に不在")
            sys.exit(1)
        info(f"OK ffmpeg ({shutil.which('ffmpeg')})")
    else:
        check_preconditions()

    info(f"\n[1/4] AivisSpeech で {len(SCENES)} scene の raw narration WAV 生成 (padding は phase 3 で)")
    for scene in SCENES:
        raw = TEMP_DIR / f"{scene.id}_raw.wav"
        wav_bytes = aivis_synthesize(scene.narration)
        raw.write_bytes(wav_bytes)
        scene.raw_duration = ffprobe_duration(raw)
        info(f"  [{scene.id}] raw_duration={scene.raw_duration:.2f}s ({scene.narration[:25]}...)")

    if narration_only:
        info("\n[narration-only fallback] padded WAV を legacy fixed lead で build")
        padded_wavs: list[Path] = []
        for scene in SCENES:
            raw = TEMP_DIR / f"{scene.id}_raw.wav"
            padded = TEMP_DIR / f"{scene.id}_padded.wav"
            scene.duration = round(scene.raw_duration + LEAD_IN_SEC + TRAIL_OUT_SEC + 0.3, 1)
            make_padded_wav(scene, raw, padded)
            padded_wavs.append(padded)
        narration_wav = TEMP_DIR / "narration_full.wav"
        concat_narration(padded_wavs, narration_wav)
        listen_path = OUTPUT_DIR / "narration_only_preview.wav"
        shutil.copy(narration_wav, listen_path)
        total_audio = ffprobe_duration(narration_wav)
        info(f"\n=== --narration-only Done ===")
        info(f"  preview WAV: {listen_path.relative_to(BASE_DIR)} ({total_audio:.2f}s)")
        return 0

    info(f"\n[2/4] Playwright で demo flow 録画 (action-then-narration model、 scene.action_elapsed 計測)")
    webm = record_demo()
    video_dur = ffprobe_duration(webm)
    info(f"  WebM: {webm.name} = {video_dur:.2f}s")
    info(f"  action_elapsed per scene (settled state 到達 wall-clock):")
    for scene in SCENES:
        info(f"    [{scene.id}] action_elapsed={scene.action_elapsed:.2f}s")

    info(f"\n[3/4] padded WAV build (lead_in = action_elapsed + {SETTLE_BUFFER_SEC}s settle buffer)")
    padded_wavs: list[Path] = []
    for scene in SCENES:
        raw = TEMP_DIR / f"{scene.id}_raw.wav"
        padded = TEMP_DIR / f"{scene.id}_padded.wav"
        lead = scene.action_elapsed + SETTLE_BUFFER_SEC
        scene.duration = round(lead + scene.raw_duration + TRAIL_OUT_SEC, 2)
        make_padded_wav(scene, raw, padded, lead_in_sec=lead)
        padded_wavs.append(padded)
        info(f"  [{scene.id}] lead={lead:.2f}s + raw={scene.raw_duration:.2f}s + trail={TRAIL_OUT_SEC}s = scene.duration={scene.duration}s")

    narration_wav = TEMP_DIR / "narration_full.wav"
    concat_narration(padded_wavs, narration_wav)
    total_audio = ffprobe_duration(narration_wav)
    info(f"  narration 結合完了: {narration_wav.name} = {total_audio:.2f}s (video {video_dur:.2f}s と 同期想定)")

    info("\n[4/4] ffmpeg で MP4 最終合成 + 末尾クレジット overlay + SRT burn-in")
    out_mp4 = OUTPUT_DIR / "mais_deal_matching_demo.mp4"
    compose_final(webm, narration_wav, out_mp4)
    final_dur = ffprobe_duration(out_mp4)
    size_mb = out_mp4.stat().st_size / 1024 / 1024
    info(f"  完成: {out_mp4} = {final_dur:.2f}s / {size_mb:.1f} MB")

    info("\n=== Done ===")
    info(f"動画 = {out_mp4.relative_to(BASE_DIR)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
