import argparse
import os
import signal
import subprocess
import sys
import time
from typing import Optional
import urllib.error
import urllib.request


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7861


def is_listening(host: str, port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/", timeout=1):
            return True
    except urllib.error.HTTPError:
        return True
    except OSError:
        return False


def request_graceful_shutdown(host: str, port: int) -> None:
    for path in ("/shutdown", "/close"):
        request = urllib.request.Request(f"http://{host}:{port}{path}", method="POST")
        try:
            urllib.request.urlopen(request, timeout=2).close()
        except OSError:
            pass


def find_windows_pid(port: int) -> Optional[int]:
    result = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True, check=False)
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[1].endswith(f":{port}") and parts[3] == "LISTENING":
            return int(parts[-1])
    return None


def find_unix_pid(port: int) -> Optional[int]:
    result = subprocess.run(["lsof", "-ti", f"tcp:{port}"], capture_output=True, text=True, check=False)
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.isdigit():
            return int(line)
    return None


def kill_pid(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False)
    else:
        os.kill(pid, signal.SIGTERM)


def shutdown(host: str, port: int, wait_seconds: float) -> int:
    if not is_listening(host, port):
        print(f"No Gradio server appears to be running on {host}:{port}.")
        return 0

    request_graceful_shutdown(host, port)
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if not is_listening(host, port):
            print(f"Stopped Gradio server on {host}:{port}.")
            return 0
        time.sleep(0.25)

    pid = find_windows_pid(port) if os.name == "nt" else find_unix_pid(port)
    if pid is None:
        print(f"Could not find the process listening on port {port}.", file=sys.stderr)
        return 1

    kill_pid(pid)
    print(f"Terminated process {pid} on {host}:{port}.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Stop the local Gradio dashboard.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--wait", type=float, default=3.0)
    args = parser.parse_args()
    return shutdown(args.host, args.port, args.wait)


if __name__ == "__main__":
    raise SystemExit(main())
