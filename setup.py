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
        install.run(self)
        self.install_deno()

    def install_deno(self):
        try:
            subprocess.run(['deno', '--version'], capture_output=True, check=True)
            print("✅ Deno is already installed.")
            return
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("⚠️  Deno not found. Installing Deno...")
            install_script = 'curl -fsSL https://deno.land/install.sh | sh'
            try:
                subprocess.run(install_script, shell=True, check=True)
                print("✅ Deno installed successfully.")
                print("   Please restart your terminal or run: export PATH=\"$HOME/.deno/bin:$PATH\"")
            except subprocess.CalledProcessError as e:
                print(f"❌ Failed to install Deno: {e}")
                print("   Please install manually: https://deno.land/#installation")

# Read README
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="lecture-manager",
    version="2.6.0.1",                     # bumped version
    description="Unified media manager for YouTube lectures, Facebook content, and offline article reading via Instapaper",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Udaya Raj Joshi",
    author_email="udayarajjoshi@gmail.com",
    url="https://github.com/blee-design/lecture-manager",
    include_package_data=True,
    packages=find_packages(),
    install_requires=[
        # Core database and media
        "mysql-connector-python>=8.0.0",
        "yt-dlp>=2023.0.0",
        "flask>=2.0.0",
        "browser-cookie3>=0.1.0",
        "bgutil-ytdlp-pot-provider>=0.0.1",
        "requests>=2.25.0",
        "gallery-dl>=1.20.0",
        "ffmpeg-python>=0.2.0",
        "curl-cffi>=0.5.0",

        # YouTube upload
        "google-api-python-client>=2.0.0",
        "google-auth-oauthlib>=0.4.0",
        "tqdm>=4.60.0",

        # HTML/text processing (question bank & article reader)
        "beautifulsoup4>=4.9.0",
        "html2text>=2020.1.16",
        "tabulate>=0.8.9",

        # Article extraction (Instapaper offline reader)
        "readability-lxml>=0.8.1",
        "lxml>=4.9.0",

        # OAuth for Instapaper Full API
        "requests-oauthlib>=1.3.0",

        # Optional: for domain extraction in tags (if you implement auto-tagging)
        # "tldextract>=3.0.0",
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
    python_requires=">=3.8",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Operating System :: Microsoft :: Windows",
    ],
)
