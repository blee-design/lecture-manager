# File: setup.py

#!/usr/bin/env python3

import subprocess
import sys
import os
from setuptools import setup, find_packages
from setuptools.command.install import install

class InstallWithDeno(install):
    """Custom install command that also installs Deno if not present."""
    def run(self):
        # Run normal install
        install.run(self)
        # Now check for Deno and install if missing
        self.install_deno()

    def install_deno(self):
        # Check if deno is available
        try:
            subprocess.run(['deno', '--version'], capture_output=True, check=True)
            print("✅ Deno is already installed.")
            return
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("⚠️  Deno not found. Installing Deno...")
            # Use the official installation script
            install_script = 'curl -fsSL https://deno.land/install.sh | sh'
            try:
                subprocess.run(install_script, shell=True, check=True)
                print("✅ Deno installed successfully.")
                print("   Please restart your terminal or run: export PATH=\"$HOME/.deno/bin:$PATH\"")
            except subprocess.CalledProcessError as e:
                print(f"❌ Failed to install Deno: {e}")
                print("   Please install manually: https://deno.land/#installation")

setup(
    name="youtube-lecture-manager",
    version="2.3.0",
    description="Organise and manage YouTube lecture libraries with a terminal interface, web UI, and local playback",
    long_description=open("README.md").read() if open("README.md").read() else "",
    long_description_content_type="text/markdown",
    author="Udaya Raj Joshi",
    author_email="udayarajjoshi@gmail.com",
    url="https://github.com/yourusername/lecture-manager",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "mysql-connector-python>=8.0.0",
        "yt-dlp>=2023.0.0",
        "flask>=2.0.0",
        "browser-cookie3",
        "bgutil-ytdlp-pot-provider",
        "requests>=2.25.0",           # For thumbnail download
        "gallery-dl>=1.20.0",          # For Facebook photo albums (optional)
        "ffmpeg-python>=0.2.0",        # Optional, but some use it; we rely on system ffmpeg
    ],
    extras_require={
        "dev": ["pytest", "black", "flake8"],
    },
    entry_points={
        "console_scripts": [
            "lecture-manager = lecture_manager.main:main",
        ],
    },
    cmdclass={
        'install': InstallWithDeno,
    },
    python_requires=">=3.6",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
    ],
)
