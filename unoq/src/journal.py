"""Journal CSV des detections (horodatage, score, son joue).
Ouvre le fichier en mode ajout au demarrage et ecrit une ligne a chaque detection confirmee.
Cree le fichier avec l'en-tete si il n'existe pas encore."""
import csv
from datetime import datetime
from pathlib import Path


class Journal:
    def __init__(self, chemin):
        self.chemin = Path(chemin).expanduser()
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        nouveau = not self.chemin.exists()
        self._f = open(self.chemin, "a", newline="", encoding="utf-8")
        self._w = csv.writer(self._f)
        if nouveau:
            self._w.writerow(["horodatage", "score", "son_joue"])
            self._f.flush()

    def detection(self, score, son_joue):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._w.writerow([ts, f"{score:.3f}", int(son_joue)])
        self._f.flush()
