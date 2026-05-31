import socket
from pathlib import Path

from app import build_dashboard


def first_free_port(start: int = 7861, stop: int = 7870) -> int:
    for port in range(start, stop + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError(f"No free local port found from {start} to {stop}.")


if __name__ == "__main__":
    port = first_free_port()
    url = f"http://127.0.0.1:{port}"
    Path(__file__).with_name("dashboard_local_url.txt").write_text(url, encoding="utf-8")
    print(url)
    build_dashboard().launch(server_name="127.0.0.1", server_port=port, inbrowser=False)
