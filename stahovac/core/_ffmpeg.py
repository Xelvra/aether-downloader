"""FFmpeg: sestavení příkazů pro ořez/ranged stahování a sledování procesu.

Vyděleno z `core/downloader.py` (audit §6.1). `FfmpegTrimMixin` se míchá do
`Downloader`; na `stahovac.core.downloader` se odkazujeme přes ``dl_mod``
za běhu kvůli monkeypatchování v testech. ``import dl_mod`` je schválně až
na konci souboru.
"""

import re
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path
from queue import Empty, Queue

from stahovac.config.constants import END_OPTION_FULL
from stahovac.core.validator import pad_time, time_to_seconds
from stahovac.utils.paths import truncate_filename

_RE_FFMPEG_TIME = re.compile(r"time=(\d+):(\d+):(\d+)")


def _fmt_timestamp(value: str) -> str:
    parts = value.split(":")
    if len(parts) == 3:
        return f"{parts[0]}h{parts[1]}m{parts[2]}s"
    if len(parts) == 2:
        return f"{parts[0]}m{parts[1]}s"
    return f"{parts[0]}s"


def _estimate_cut_duration(start_time: str, end_time: str, end_option: str | None) -> int | None:
    if not end_option or end_option == END_OPTION_FULL:
        return None
    return max(0, time_to_seconds(end_time) - time_to_seconds(start_time))


def _ffmpeg_timeout(estimated_secs: int | None, re_encode: bool) -> float:
    if estimated_secs and estimated_secs > 0:
        factor = 5 if re_encode else 2
        return max(60.0, estimated_secs * factor + 60.0)
    return 7200.0


def _build_ffmpeg_cmd(
    input_path: Path,
    start_time: str,
    end_time: str,
    end_option: str,
    re_encode: bool = False,
    crf: int = 23,
    preset: str = "fast",
    ffmpeg_bin: str = "ffmpeg",
) -> tuple[list[str], Path]:
    start_padded = pad_time(start_time)
    start_safe = _fmt_timestamp(start_padded)

    if end_option == END_OPTION_FULL:
        to_arg: str | None = None
        section_part = f" [{start_safe}-inf]"
    else:
        to_arg = pad_time(end_time)
        end_safe = _fmt_timestamp(to_arg)
        section_part = f" [{start_safe} - {end_safe}]"

    output_path = input_path.with_name(f"{truncate_filename(input_path.stem)}{section_part}{input_path.suffix}")

    if re_encode:
        cmd = [ffmpeg_bin, "-y", "-i", str(input_path), "-ss", start_padded]
        if to_arg:
            cmd.extend(["-to", to_arg])
        cmd.extend(["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-c:a", "aac"])
    else:
        cmd = [ffmpeg_bin, "-y", "-ss", start_padded, "-i", str(input_path)]
        if to_arg:
            cmd.extend(["-to", to_arg])
        cmd.extend(["-c", "copy", "-avoid_negative_ts", "make_zero"])
    cmd.extend(["-movflags", "+faststart", str(output_path)])
    return cmd, output_path


def _headers_args(headers: dict) -> list[str]:
    if not headers:
        return []
    value = "".join(f"{k}: {v}\r\n" for k, v in headers.items())
    return ["-headers", value]


def _hls_input_args(fmt: dict) -> list[str]:
    args = ["-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5"]
    args += _headers_args(fmt.get("http_headers") or {})
    args += ["-i", fmt["url"]]
    return args


def _build_ranged_cmd(
    video_fmt: dict,
    audio_fmt: dict | None,
    start_time: str,
    end_time: str,
    end_option: str,
    re_encode: bool,
    crf: int,
    preset: str,
    output_path: Path,
    ffmpeg_bin: str,
) -> list[str]:
    """FFmpeg příkaz, který z HLS streamu stáhne jen segmenty v časovém rozsahu."""
    cmd = [ffmpeg_bin, "-y", "-ss", pad_time(start_time)]
    cmd += _hls_input_args(video_fmt)
    if audio_fmt is not None:
        cmd += _hls_input_args(audio_fmt)
    if end_option != END_OPTION_FULL:
        duration = max(0, time_to_seconds(end_time) - time_to_seconds(start_time))
        cmd += ["-t", str(duration)]
    if re_encode:
        cmd += ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-c:a", "aac"]
    else:
        cmd += ["-c", "copy", "-bsf:a", "aac_adtstoasc", "-avoid_negative_ts", "make_zero"]
    cmd += ["-movflags", "+faststart", str(output_path)]
    return cmd


class FfmpegTrimMixin:
    _cancel_event: threading.Event
    on_log: Callable[[str], None]
    on_progress: Callable[[str, float, str, str], None]

    def _cut_with_ffmpeg(
        self,
        input_path: Path,
        start_time: str,
        end_time: str,
        end_option: str,
        re_encode: bool = False,
        crf: int = 23,
        preset: str = "fast",
        job_id: str = "",
    ) -> Path | None:
        ffmpeg_bin = dl_mod.find_ffmpeg()
        if ffmpeg_bin is None:
            self.on_log("FFmpeg není nainstalován. Ořez není možný.")
            return None

        cmd, output_path = _build_ffmpeg_cmd(
            input_path,
            start_time,
            end_time,
            end_option,
            re_encode=re_encode,
            crf=crf,
            preset=preset,
            ffmpeg_bin=str(ffmpeg_bin),
        )
        self.on_log(f"Ořezávám: {dl_mod._sanitize_cmd(cmd)}")
        proc = dl_mod.subprocess.Popen(
            cmd,
            stdout=dl_mod.subprocess.DEVNULL,
            stderr=dl_mod.subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        dl_mod._track_process(proc)
        try:
            estimated = _estimate_cut_duration(start_time, end_time, end_option)
            ok = self._run_ffmpeg(proc, estimated, re_encode, job_id)
            if ok and output_path.exists():
                return output_path
            return None
        finally:
            dl_mod._untrack_process(proc)

    def _run_ffmpeg(self, proc: subprocess.Popen, estimated_secs: int | None, re_encode: bool, job_id: str) -> bool:
        """Spustí FFmpeg a sleduje průběh.

        Výstup se čte v samostatném vlákně, takže cyklus pravidelně
        kontroluje zrušení a časový limit i v případě, kdy FFmpeg dočasně
        neposílá žádný výstup (na rozdíl od blokujícího ``readline()``).
        """
        started = dl_mod.time.time()
        timeout = _ffmpeg_timeout(estimated_secs, re_encode)
        lines: Queue[str] = Queue()
        stopped = threading.Event()

        def _read_stderr():
            stderr = proc.stderr
            try:
                if stderr is not None:
                    while True:
                        line = stderr.readline()
                        if not line:
                            break
                        text = line.decode("utf-8", errors="replace") if isinstance(line, bytes) else str(line)
                        lines.put(text)
            except (OSError, ValueError):
                pass
            finally:
                stopped.set()

        if self._cancel_event.is_set():
            self.on_log("Ořez zrušen uživatelem")
            dl_mod._kill_process(proc)
            return False

        reader = threading.Thread(target=_read_stderr, name="ffmpeg-stderr", daemon=True)
        reader.start()

        while True:
            if self._cancel_event.is_set():
                self.on_log("Ořez zrušen uživatelem")
                dl_mod._kill_process(proc)
                stopped.set()
                reader.join(timeout=1)
                return False
            if dl_mod.time.time() - started > timeout:
                self.on_log("Ořezávání přesáhlo časový limit, ukončuji.")
                dl_mod._kill_process(proc)
                stopped.set()
                reader.join(timeout=1)
                return False
            try:
                text = lines.get(timeout=0.2)
            except Empty:
                if stopped.is_set() and lines.empty():
                    break
                continue
            m = _RE_FFMPEG_TIME.search(text)
            if m and estimated_secs and estimated_secs > 0:
                hours, minutes, seconds = (int(g) for g in m.groups())
                elapsed = hours * 3600 + minutes * 60 + seconds
                percent = min(100.0, elapsed / estimated_secs * 100)
                self.on_progress(job_id, percent, "–", "–")

        try:
            proc.wait(timeout=10)
        except (OSError, dl_mod.subprocess.TimeoutExpired):
            dl_mod._kill_process(proc)
            return False
        return proc.returncode == 0


import stahovac.core.downloader as dl_mod  # noqa: E402  (cyklický import – jen runtime přístup)
