"""
NQNghia Tools - Quick Launcher
Double click this file or run: python run.py
"""
import subprocess
import sys
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Check & install dependencies
PACKAGES = ["yt-dlp", "requests", "pdf2docx", "docx2pdf", "Pillow", "rembg[cpu]", "PyPDF2", "python-docx"]

try:
    import yt_dlp
    import requests
except ImportError:
    print("Đang cài đặt dependencies...")
    subprocess.check_call([sys.executable, "-m", "pip", "install"] + PACKAGES)

# Start server
print("Đang khởi động NQNghia Tools...")
subprocess.call([sys.executable, "api_server.py"])
