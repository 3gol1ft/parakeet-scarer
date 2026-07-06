"""Test de detection en direct sur la webcam (sans filtrage, sans son).
Affiche le score brut image par image pour calibrer le seuil de detection."""
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent / "src"))
from camera import Camera
from detector_eim import PerrucheDetectorEIM


def main():
    with Camera() as cam, PerrucheDetectorEIM() as detector:
        print("Détection en cours — Ctrl+C pour arrêter.", flush=True)
        for _ in range(5):
            cam.read()
        while True:
            frame = cam.read()
            if frame is None:
                continue
            scores = detector.predict(frame)
            p = scores.get("perruche", 0.0)
            barre = "#" * int(p * 20)
            print(f"perruche: {p:0.3f} [{barre:<20}]  "
                  f"pas_perruche: {scores.get('pas_perruche', 0.0):0.3f}",
                  flush=True)
            time.sleep(0.2)


if __name__ == "__main__":
    main()
