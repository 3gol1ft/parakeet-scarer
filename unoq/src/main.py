"""Version console du systeme d'effarouchement (sans dashboard web).
Utile pour deboguer en SSH sans demarrer Flask. Tous les reglages viennent de config.yaml.
En production, preferer web_demo.py qui est lance par le service systemd."""
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2

sys.path.append(str(Path(__file__).resolve().parent))
from config import CFG, chemin
from camera import Camera
from detector_eim import PerrucheDetectorEIM
from decision import Decision
from ble_client import EffaroucheurBLE

D = CFG["detection"]
C = CFG["camera"]
B = CFG["ble"]
DOSSIER = chemin("detections")


def main():
    DOSSIER.mkdir(parents=True, exist_ok=True)
    decision = Decision(
        seuil=D["seuil"], n_requis=D["n_requis"],
        fenetre=D["fenetre"], n_perte=D["n_perte"],
    )
    ble = EffaroucheurBLE(nom=B["nom"], carac_uuid=B["carac_uuid"])
    ble.start()
    dernier_son = 0.0
    total = 0

    with Camera(width=C["largeur"], height=C["hauteur"], focus=C["focus"]) as cam, \
            PerrucheDetectorEIM() as detector:
        print("Systeme demarre. Ctrl+C pour arreter.", flush=True)
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
                print(f"[{total}] PERRUCHE detectee {score:.2f} -> photo {nom}", flush=True)

                if time.time() - dernier_son >= D["cooldown_s"]:
                    if ble.trigger():
                        dernier_son = time.time()
                        print("    -> SON d'effarouchement declenche", flush=True)
                else:
                    print("    -> son en pause (cooldown)", flush=True)

            time.sleep(0.1)


if __name__ == "__main__":
    main()
