"""Outil de test : photographie chaque detection confirmee sans declencher le son.
Les reglages de detection viennent de config.yaml.
Utile pour recolter des donnees de terrain et calibrer le seuil."""
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2

sys.path.append(str(Path(__file__).resolve().parent.parent / "src"))
from config import CFG, chemin
from camera import Camera
from detector_eim import PerrucheDetectorEIM
from decision import Decision

D = CFG["detection"]
C = CFG["camera"]
DOSSIER = chemin("detections")


def main():
    DOSSIER.mkdir(parents=True, exist_ok=True)
    decision = Decision(
        seuil=D["seuil"], n_requis=D["n_requis"],
        fenetre=D["fenetre"], n_perte=D["n_perte"],
    )
    total = 0
    with Camera(width=C["largeur"], height=C["hauteur"], focus=C["focus"]) as cam, \
            PerrucheDetectorEIM() as detector:
        print(f"Surveillance (seuil={D['seuil']}, {D['n_requis']}/{D['fenetre']}). Ctrl+C.", flush=True)
        for _ in range(5):
            cam.read()
        while True:
            frame = cam.read()
            if frame is None:
                continue
            score = detector.predict(frame).get("perruche", 0.0)
            present, evenement = decision.update(score)
            if evenement:
                total += 1
                ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                nom = f"{ts}_perruche_{score:.2f}.jpg"
                cv2.imwrite(str(DOSSIER / nom), frame)
                print(f"[{total}] PERRUCHE confirmee {score:.2f} -> {nom}", flush=True)
            time.sleep(0.1)


if __name__ == "__main__":
    main()
