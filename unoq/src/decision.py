"""Logique de decision anti-faux-positifs.
Deux reglages independants :
  - seuil              : surete PAR image (sensibilite)
  - n_requis / fenetre : combien d'images recentes doivent passer (persistance)
Hysteresis : une fois confirmee, on garde la perruche meme si le score
plonge brievement (evite de 'perdre' un oiseau clairement present)."""
from collections import deque


class Decision:
    def __init__(self, seuil=0.70, n_requis=3, fenetre=6, n_perte=5):
        self.seuil = seuil
        self.n_requis = n_requis
        self.n_perte = n_perte
        self.historique = deque(maxlen=fenetre)
        self.absences = 0
        self.present = False

    def update(self, score):
        """Renvoie (present, evenement)."""
        vu = score >= self.seuil
        self.historique.append(vu)
        self.absences = 0 if vu else self.absences + 1

        evenement = False
        if not self.present:
            if sum(self.historique) >= self.n_requis:   # apparition
                self.present = True
                evenement = True
        else:
            if self.absences >= self.n_perte:           # disparition
                self.present = False
        return self.present, evenement
