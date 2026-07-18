#!/usr/bin/env python3
"""Helper to check/install Ollama models for local use with Jarvis.

Usage:
  python setup_ollama.py --list
  python setup_ollama.py --pull mistral
  python setup_ollama.py --check-server

This script does not install Ollama itself. Install Ollama per the
official instructions for your platform, then use this helper to pull
models and validate the local Ollama server.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import urllib.request

DEFAULT_MODEL = "mistral"
DEFAULT_API = "http://localhost:11434"


def has_ollama_binary() -> bool:
    return shutil.which("ollama") is not None


def run_ollama_command(args: list[str]) -> int:
    try:
        return subprocess.run(["ollama"] + args, check=False).returncode
    except FileNotFoundError:
        print("ollama binary not found on PATH.")
        return 2


def list_models() -> None:
    if not has_ollama_binary():
        print("ollama not found. Please install Ollama and ensure 'ollama' is on PATH.")
        return
    print("Listing models via 'ollama list'...\n")
    run_ollama_command(["list"])  # prints to stdout/stderr


def pull_model(model: str) -> None:
    if not has_ollama_binary():
        print("ollama not found. Please install Ollama and ensure 'ollama' is on PATH.")
        return
    print(f"Pulling model: {model} (this may take a while)...")
    rc = run_ollama_command(["pull", model])
    if rc == 0:
        print("Model pulled successfully.")
    else:
        print(f"'ollama pull {model}' exited with code {rc}.")


def check_server(api_url: str) -> None:
    print(f"Checking Ollama API at {api_url}...")
    probe_url = api_url.rstrip("/") + "/api/tags"
    try:
        req = urllib.request.Request(probe_url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = resp.read().decode("utf-8")
            try:
                parsed = json.loads(data)
                print("Server responded, sample output:")
                print(json.dumps(parsed, indent=2)[:2000])
            except Exception:
                print("Server responded but output was not JSON:")
                print(data[:2000])
    except Exception as e:
        print("Could not reach Ollama server:", e)
        print("If you installed Ollama, start the daemon per Ollama docs or ensure OLLAMA_API_URL is correct.")


def main() -> int:
    p = argparse.ArgumentParser(description="Ollama helper for Jarvis")
    p.add_argument("--list", action="store_true", help="Run 'ollama list'")
    p.add_argument("--pull", metavar="MODEL", help="Pull a model (e.g. mistral)")
    p.add_argument("--check-server", action="store_true", help="Query local Ollama API (/api/tags)")
    p.add_argument("--api", default=DEFAULT_API, help="Ollama API base URL")
    args = p.parse_args()

    if args.list:
        list_models()
        return 0
    if args.pull:
        pull_model(args.pull)
        return 0
    if args.check_server:
        check_server(args.api)
        return 0

    p.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
