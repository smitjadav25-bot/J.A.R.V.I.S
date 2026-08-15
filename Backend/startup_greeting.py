import datetime

from services.local_speaker import speak


def startup_greeting() -> None:
    hour = datetime.datetime.now().hour
    if 5 <= hour < 12:
        greeting = "Good morning"
    elif 12 <= hour < 17:
        greeting = "Good afternoon"
    elif 17 <= hour < 21:
        greeting = "Good evening"
    else:
        greeting = "Good night"
    speak(f"{greeting} sir. I am Jarvis. What can I help you with today?")


if __name__ == "__main__":
    startup_greeting()
