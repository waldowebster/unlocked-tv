"""Create original, compact media fixtures for first-boot playback and slideshow testing."""
from pathlib import Path
import math
import os
import subprocess

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame

root = Path(__file__).resolve().parents[1] / "assets"
root.mkdir(exist_ok=True)
pygame.font.init()
for name, palette in [("01 Coast", ("#152D40", "#3A8992", "#A8C9AE")), ("02 Dunes", ("#403E52", "#B37968", "#E8C29B"))]:
    image = pygame.Surface((1280, 720))
    image.fill(palette[0])
    for layer, color in enumerate(palette[1:]):
        points = [(0, 720)]
        for x in range(0, 1281, 4):
            y = 375 + layer*140 + 65*math.sin(x/240 + layer*1.4)
            points.append((x, y))
        points += [(1280, 720)]
        pygame.draw.polygon(image, color, points)
    pygame.draw.circle(image, "#F1DEB9", (970, 160), 55)
    pygame.image.save(image, root / f"{name}.png")
subprocess.run([
    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-loop", "1", "-i", str(root / "01 Coast.png"),
    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "20", "-r", "24",
    "-vf", "drawbox=x=40:y=650:w=1200:h=6:color=white@0.3:t=fill",
    "-af", "volume=0.08", "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-pix_fmt", "yuv420p",
    "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart", str(root / "Welcome.mp4"),
], check=True)
