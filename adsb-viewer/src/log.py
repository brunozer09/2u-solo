DEBUG_FLAG = True


def log(msg: str) -> None:
    print(f"[LOG] {msg}")


def warn(msg: str) -> None:
    print(f"[WARN] {msg}")


def error(msg: str) -> None:
    print(f"[ERROR] {msg}")


def debug(msg: str) -> None:
    if DEBUG_FLAG:
        print(f"[DEBUG] {msg}")
