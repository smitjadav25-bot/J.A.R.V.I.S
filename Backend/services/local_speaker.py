import platform
import subprocess


def speak(text: str) -> None:
    if platform.system() != "Darwin":
        return
    cleaned = (text or "").strip()
    if not cleaned:
        return
    subprocess.Popen(["say", cleaned])
