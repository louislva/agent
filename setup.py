#!/usr/bin/env python3

from setuptools import setup

with open("requirements.txt", "r") as f:
    requirements = [line.strip() for line in f if line.strip() and not line.startswith("#")]

setup(
    name="agent-vm",
    version="1.0.0",
    description="Minimalist agentic coding tool with Linode VM management",
    author="Your Name",
    author_email="your.email@example.com",
    py_modules=["agent"],
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "agent=agent:main",
        ],
    },
    python_requires=">=3.7",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
)