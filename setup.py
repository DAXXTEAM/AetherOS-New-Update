"""AetherOS v3.0   The Singularity   Setup Configuration."""
from setuptools import setup, find_packages

setup(
    name="aetheros",
    version="3.0.0",
    author="Arpit-DAXX",
    author_email="admin@daxxteam.io",
    description="Ultra-Advanced Autonomous AI Agent Operating System",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/DAXXTEAM/AetherOS-New-Update",
    packages=find_packages(),
    python_requires=">=3.11",
    classifiers=[
        "Programming Language :: Python :: 3.11",
        "Operating System :: OS Independent",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Development Status :: 4 - Beta",
    ],
    entry_points={
        "console_scripts": [
            "aetheros=aetheros:main",
        ],
    },
)
