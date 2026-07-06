"""Test de la webcam : mesure le FPS reel sur 100 images et enregistre une photo de controle.
Les parametres camera (resolution, mise au point) viennent de config.yaml."""
import sys
import time
from pathlib import Path

import cv2

sys.path.append(str(Path(__file__).resolve().parent.parent / "src"))
from config import CFG, chemin
from camera import Camera

N_FRAMES = 100
OUTPUT = Path.home() / "effaroucheur-perruches/unoq/tests_data/test_opencv.jpg"


def main():
    C = CFG["camera"]
    with Camera(width=C["largeur"], height=C["hauteur"], focus=C["focus"]) as cam:
        # on laisse la camera chauffer (premieres images parfois noires)
        for _ in range(5):
            cam.read()

        start = time.time()
        last_frame, count = None, 0
        for _ in range(N_FRAMES):
            frame = cam.read()
            if frame is None:
                continue
            last_frame, count = frame, count + 1

        elapsed = time.time() - start
        fps = count / elapsed if elapsed > 0 else 0
        print(f"{count} images en {elapsed:.1f} s  ->  {fps:.1f} FPS")

        if last_frame is not None:
            h, w = last_frame.shape[:2]
            print(f"Resolution reelle : {w}x{h}")
            cv2.imwrite(str(OUTPUT), last_frame)
            print(f"Image enregistree : {OUTPUT}")
        else:
            print("Aucune image valide - verifie le peripherique.")


if __name__ == "__main__":
    main()
