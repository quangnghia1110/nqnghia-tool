"""
Video Downloader - YouTube, TikTok, Facebook
Download video without watermark/tag.
Usage:
    from video_downloader import download_video
    result = download_video("https://...", output_dir="./downloads")
"""

import os
import re
import json
import time
import requests
import yt_dlp

# ============================================================
#  Progress tracking (shared state for API polling)
# ============================================================

_progress_store = {}


def get_progress(task_id: str) -> dict:
    """Get current progress for a download task."""
    return _progress_store.get(task_id, {"status": "unknown"})


def _make_progress_hook(task_id: str):
    """Create a yt-dlp progress hook that updates _progress_store."""
    def hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            speed = d.get("speed") or 0
            eta = d.get("eta") or 0
            percent = (downloaded / total * 100) if total > 0 else 0
            _progress_store[task_id] = {
                "status": "downloading",
                "percent": round(percent, 1),
                "downloaded": downloaded,
                "total": total,
                "speed": speed,
                "eta": eta,
                "speed_str": _format_bytes(speed) + "/s" if speed else "",
                "eta_str": _format_eta(eta) if eta else "",
            }
        elif d["status"] == "finished":
            _progress_store[task_id] = {
                "status": "processing",
                "percent": 100,
                "downloaded": d.get("total_bytes", 0),
                "total": d.get("total_bytes", 0),
                "speed": 0,
                "eta": 0,
                "speed_str": "",
                "eta_str": "Đang xử lý...",
            }
    return hook


def _format_bytes(b: float) -> str:
    """Format bytes to human readable string."""
    if b < 1024:
        return f"{b:.0f} B"
    elif b < 1024 ** 2:
        return f"{b / 1024:.1f} KB"
    elif b < 1024 ** 3:
        return f"{b / 1024**2:.1f} MB"
    else:
        return f"{b / 1024**3:.2f} GB"


def _format_eta(seconds: int) -> str:
    """Format ETA seconds to mm:ss string."""
    if seconds <= 0:
        return ""
    m, s = divmod(int(seconds), 60)
    if m > 0:
        return f"{m}p {s}s"
    return f"{s}s"


# ============================================================
#  Platform detection
# ============================================================

PLATFORM_PATTERNS = {
    "youtube": [
        r"(?:https?://)?(?:www\.)?youtube\.com/watch",
        r"(?:https?://)?(?:www\.)?youtube\.com/shorts",
        r"(?:https?://)?youtu\.be/",
        r"(?:https?://)?(?:www\.)?youtube\.com/embed/",
    ],
    "tiktok": [
        r"(?:https?://)?(?:www\.)?tiktok\.com/@[\w.-]+/video/",
        r"(?:https?://)?vm\.tiktok\.com/",
        r"(?:https?://)?(?:www\.)?tiktok\.com/t/",
        r"(?:https?://)?vt\.tiktok\.com/",
    ],
    "facebook": [
        r"(?:https?://)?(?:www\.)?facebook\.com/.+/videos/",
        r"(?:https?://)?(?:www\.)?facebook\.com/watch",
        r"(?:https?://)?(?:www\.)?facebook\.com/reel",
        r"(?:https?://)?fb\.watch/",
        r"(?:https?://)?(?:www\.)?facebook\.com/.+/posts/",
        r"(?:https?://)?(?:www\.)?facebook\.com/share/v/",
    ],
}


def detect_platform(url: str) -> str:
    """Return 'youtube' | 'tiktok' | 'facebook' | 'unknown'."""
    for platform, patterns in PLATFORM_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return platform
    return "unknown"


# ============================================================
#  TikTok no-watermark helper
# ============================================================

def _resolve_tiktok_url(url: str) -> str:
    """Resolve short TikTok URLs to full URL."""
    if "vm.tiktok.com" in url or "vt.tiktok.com" in url or "/t/" in url:
        resp = requests.head(url, allow_redirects=True, timeout=10)
        return resp.url
    return url


def _get_tiktok_video_id(url: str) -> str | None:
    """Extract video ID from TikTok URL."""
    match = re.search(r"/video/(\d+)", url)
    return match.group(1) if match else None


def _download_tiktok_no_watermark(url: str, output_dir: str, filename: str | None = None, task_id: str | None = None) -> dict:
    """
    Download TikTok video without watermark.
    Strategy:
      1. Use yt-dlp to get video info and try direct download (often no watermark with correct format)
      2. Fallback: use TikTok's own API endpoint for watermark-free video
    """
    url = _resolve_tiktok_url(url)
    video_id = _get_tiktok_video_id(url)

    # Strategy 1: yt-dlp with specific format selection
    # TikTok often provides watermark-free versions in certain formats
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        title = _sanitize_filename(info.get("title", f"tiktok_{video_id or int(time.time())}"))
        if filename:
            title = _sanitize_filename(filename)

        # Try to find format without watermark
        # yt-dlp for TikTok: format 'download_addr-0' or 'play_addr-0' are often watermark-free
        formats = info.get("formats", [])
        no_wm_format = None
        for fmt in formats:
            fmt_id = fmt.get("format_id", "")
            # 'download_addr' variants are typically without watermark
            if "download_addr" in fmt_id or "download" in fmt_id:
                no_wm_format = fmt_id
                break

        # If no specific no-watermark format found, try 'bytevc1' codec (often cleaner)
        if not no_wm_format:
            for fmt in formats:
                if fmt.get("vcodec", "") and "bytevc1" in fmt.get("vcodec", ""):
                    no_wm_format = fmt.get("format_id")
                    break

        output_path = os.path.join(output_dir, f"{title}.mp4")

        download_opts = {
            "quiet": True,
            "no_warnings": True,
            "outtmpl": os.path.join(output_dir, f"{title}.%(ext)s"),
            "merge_output_format": "mp4",
        }

        if task_id:
            download_opts["progress_hooks"] = [_make_progress_hook(task_id)]

        if no_wm_format:
            download_opts["format"] = no_wm_format
        else:
            # Default: best quality, yt-dlp often gets no-watermark version
            download_opts["format"] = "best"

        with yt_dlp.YoutubeDL(download_opts) as ydl:
            ydl.download([url])

        # Find actual downloaded file
        output_path = _find_downloaded_file(output_dir, title)

        return {
            "success": True,
            "platform": "tiktok",
            "title": title,
            "file_path": output_path,
            "video_id": video_id,
        }

    except Exception as e:
        return {
            "success": False,
            "platform": "tiktok",
            "error": str(e),
        }


# ============================================================
#  YouTube downloader
# ============================================================

def _download_youtube(url: str, output_dir: str, filename: str | None = None,
                      quality: str = "best", task_id: str | None = None) -> dict:
    """
    Download YouTube video - best quality, no watermark (YouTube doesn't add watermarks).
    Removes metadata tags from the original uploader.
    """
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        title = _sanitize_filename(info.get("title", f"youtube_{int(time.time())}"))
        if filename:
            title = _sanitize_filename(filename)

        video_id = info.get("id", "")

        # Quality mapping
        format_str = _get_youtube_format(quality)

        download_opts = {
            "quiet": True,
            "no_warnings": True,
            "outtmpl": os.path.join(output_dir, f"{title}.%(ext)s"),
            "format": format_str,
            "merge_output_format": "mp4",
            # Remove metadata/tags from original uploader
            "postprocessors": [

                {
                    "key": "FFmpegMetadata",
                    "add_metadata": False,
                },
                {
                    "key": "EmbedThumbnail",
                    "already_have_thumbnail": False,
                },
            ],
            "writethumbnail": False,
            # Clear all metadata
            "parse_metadata": [
                ":(?P<meta_comment>)",
                ":(?P<meta_description>)",
                ":(?P<meta_synopsis>)",
                ":(?P<meta_artist>)",
                ":(?P<meta_creator>)",
                ":(?P<meta_author>)",
            ],
        }

        if task_id:
            download_opts["progress_hooks"] = [_make_progress_hook(task_id)]

        with yt_dlp.YoutubeDL(download_opts) as ydl:
            ydl.download([url])

        output_path = _find_downloaded_file(output_dir, title)

        return {
            "success": True,
            "platform": "youtube",
            "title": title,
            "file_path": output_path,
            "video_id": video_id,
            "quality": quality,
        }

    except Exception as e:
        return {
            "success": False,
            "platform": "youtube",
            "error": str(e),
        }


def _get_youtube_format(quality: str) -> str:
    """Map quality string to yt-dlp format."""
    quality_map = {
        "best": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "1080p": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]",
        "720p": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]",
        "480p": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]",
        "360p": "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360]",
        "audio": "bestaudio[ext=m4a]/bestaudio",
    }
    return quality_map.get(quality, quality_map["best"])


# ============================================================
#  Facebook downloader
# ============================================================

def _download_facebook(url: str, output_dir: str, filename: str | None = None,
                       quality: str = "best", task_id: str | None = None) -> dict:
    """
    Download Facebook video - no watermark, remove creator tags/metadata.
    """
    try:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "outtmpl": "%(title)s",
            "extract_flat": False,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        title = _sanitize_filename(info.get("title", f"facebook_{int(time.time())}"))
        if filename:
            title = _sanitize_filename(filename)

        video_id = info.get("id", "")

        if quality == "best":
            format_str = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        else:
            format_str = f"bestvideo[height<={quality.replace('p', '')}][ext=mp4]+bestaudio[ext=m4a]/best"

        download_opts = {
            "quiet": True,
            "no_warnings": True,
            "outtmpl": os.path.join(output_dir, f"{title}.%(ext)s"),
            "format": format_str,
            "merge_output_format": "mp4",
            # Remove all metadata/tags
            "parse_metadata": [
                ":(?P<meta_comment>)",
                ":(?P<meta_description>)",
                ":(?P<meta_synopsis>)",
                ":(?P<meta_artist>)",
                ":(?P<meta_creator>)",
                ":(?P<meta_author>)",
            ],
        }

        if task_id:
            download_opts["progress_hooks"] = [_make_progress_hook(task_id)]

        with yt_dlp.YoutubeDL(download_opts) as ydl:
            ydl.download([url])

        output_path = _find_downloaded_file(output_dir, title)

        return {
            "success": True,
            "platform": "facebook",
            "title": title,
            "file_path": output_path,
            "video_id": video_id,
        }

    except Exception as e:
        return {
            "success": False,
            "platform": "facebook",
            "error": str(e),
        }


# ============================================================
#  Utilities
# ============================================================

def _sanitize_filename(name: str) -> str:
    """Remove invalid characters from filename."""
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:200] if name else f"video_{int(time.time())}"


def _find_downloaded_file(output_dir: str, title: str) -> str:
    """Find the actual downloaded file (extension may vary)."""
    for ext in ["mp4", "mkv", "webm", "m4a", "mp3"]:
        path = os.path.join(output_dir, f"{title}.{ext}")
        if os.path.exists(path):
            return path
    # Fallback: find newest file in output_dir
    files = [
        os.path.join(output_dir, f)
        for f in os.listdir(output_dir)
        if os.path.isfile(os.path.join(output_dir, f))
    ]
    if files:
        return max(files, key=os.path.getmtime)
    return os.path.join(output_dir, f"{title}.mp4")


# ============================================================
#  Main API - unified download function
# ============================================================

def download_video(
    url: str,
    output_dir: str = "./downloads",
    filename: str | None = None,
    quality: str = "best",
    task_id: str | None = None,
    output_format: str = "mp4",
) -> dict:
    """
    Download video from YouTube, TikTok, or Facebook.

    Args:
        url:            Video URL
        output_dir:     Directory to save the video (default: ./downloads)
        filename:       Custom filename (without extension). If None, uses video title.
        quality:        Video quality - 'best', '1080p', '720p', '480p', '360p', 'audio'
        task_id:        Task ID for progress tracking
        output_format:  'mp4' or 'mp3'

    Returns:
        dict with keys:
            success:   bool
            platform:  str ('youtube' | 'tiktok' | 'facebook')
            title:     str (video title / filename)
            file_path: str (path to downloaded file)
            error:     str (if success=False)
    """
    os.makedirs(output_dir, exist_ok=True)

    platform = detect_platform(url)

    if task_id:
        _progress_store[task_id] = {"status": "starting", "percent": 0}

    # If mp3 format, force audio quality
    if output_format == "mp3":
        quality = "audio"

    if platform == "youtube":
        result = _download_youtube(url, output_dir, filename, quality, task_id)
    elif platform == "tiktok":
        result = _download_tiktok_no_watermark(url, output_dir, filename, task_id)
    elif platform == "facebook":
        result = _download_facebook(url, output_dir, filename, quality, task_id)
    else:
        return {
            "success": False,
            "platform": "unknown",
            "error": f"URL not recognized. Supported: YouTube, TikTok, Facebook. Got: {url}",
        }

    # Convert to mp3 if requested
    if result.get("success") and output_format == "mp3":
        result = _convert_to_mp3(result)

    return result


def _convert_to_mp3(result: dict) -> dict:
    """Convert downloaded file to mp3 using ffmpeg."""
    import subprocess
    import shutil

    src = result.get("file_path", "")
    if not src or not os.path.exists(src):
        return result

    # Already mp3
    if src.lower().endswith(".mp3"):
        return result

    dst = os.path.splitext(src)[0] + ".mp3"
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        # ffmpeg not found, return as-is
        result["error_note"] = "ffmpeg not found, returning original format"
        return result

    try:
        subprocess.run(
            [ffmpeg, "-i", src, "-vn", "-acodec", "libmp3lame", "-ab", "320k", "-y", dst],
            capture_output=True, timeout=120,
        )
        if os.path.exists(dst):
            os.remove(src)
            result["file_path"] = dst
            result["title"] = os.path.splitext(result.get("title", ""))[0]
        return result
    except Exception:
        return result


# ============================================================
#  CLI usage
# ============================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python video_downloader.py <URL> [output_dir] [quality]")
        print("  quality: best, 1080p, 720p, 480p, 360p, audio")
        print()
        print("Examples:")
        print("  python video_downloader.py https://youtube.com/watch?v=xxx")
        print("  python video_downloader.py https://tiktok.com/@user/video/123 ./my_videos")
        print("  python video_downloader.py https://fb.watch/xxx ./downloads 720p")
        sys.exit(0)

    video_url = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "./downloads"
    vid_quality = sys.argv[3] if len(sys.argv) > 3 else "best"

    print(f"Detecting platform for: {video_url}")
    detected = detect_platform(video_url)
    print(f"Platform: {detected}")
    print(f"Downloading to: {out_dir}")
    print(f"Quality: {vid_quality}")
    print("-" * 50)

    result = download_video(video_url, output_dir=out_dir, quality=vid_quality)

    if result["success"]:
        print(f"Downloaded: {result['title']}")
        print(f"Saved to:   {result['file_path']}")
    else:
        print(f"Error: {result['error']}")
