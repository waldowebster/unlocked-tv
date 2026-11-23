"""An installable native app with persistent state and remote navigation."""
import json
import os
from pathlib import Path
import signal
import queue
import sys
import threading

import pygame

pygame.display.init()
pygame.font.init()
screen = pygame.display.set_mode((1280, 720), pygame.FULLSCREEN)
pygame.display.set_caption("Counter")
pygame.mouse.set_visible(False)
path = Path(os.environ["UNLOCKED_APP_DATA"]) / "counter.json"
try:
    count = int(json.loads(path.read_text())["count"])
except (OSError, ValueError, KeyError, TypeError):
    count = 0
running = True
inputs = queue.Queue()


def read_inputs():
    for line in sys.stdin:
        try:
            inputs.put(json.loads(line)["action"])
        except (ValueError, KeyError):
            pass


if os.environ.get("UNLOCKED_APP_INPUT") == "stdin":
    threading.Thread(target=read_inputs, daemon=True).start()


def save():
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps({"count": count}))
    temp.replace(path)


def quit_app(signum, frame):
    global running
    running = False


signal.signal(signal.SIGTERM, quit_app)
clock = pygame.time.Clock()
font = pygame.font.Font(None, 180)
label = pygame.font.Font(None, 48)
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN and os.environ.get("UNLOCKED_APP_INPUT") != "stdin":
            if event.key in {pygame.K_ESCAPE, pygame.K_HOME, pygame.K_BACKSPACE}:
                running = False
            elif event.key in {pygame.K_UP, pygame.K_RIGHT, pygame.K_RETURN}:
                count += 1
                save()
            elif event.key in {pygame.K_DOWN, pygame.K_LEFT}:
                count -= 1
                save()
    while not inputs.empty():
        action = inputs.get_nowait()
        if action in {"up", "right", "select"}:
            count += 1
            save()
        elif action in {"down", "left"}:
            count -= 1
            save()
    screen.fill("#151C25")
    text = label.render("Counter", True, "#E0A178")
    screen.blit(text, (64, 62))
    value = font.render(str(count), True, "#F1F3F7")
    screen.blit(value, value.get_rect(center=(640, 360)))
    pygame.display.flip()
    clock.tick(20)
save()
pygame.quit()
