from shutdown_local import shutdown


if __name__ == "__main__":
    raise SystemExit(shutdown("0.0.0.0", 7862, 3.0))
