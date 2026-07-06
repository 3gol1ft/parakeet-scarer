"""Inference sur le modele Edge Impulse (perruche.eim, classification 128x128).
Redimensionne chaque frame en squash (etirement) pour coller a l'entrainement du modele,
et renvoie un dict {label: score} avec la probabilite par classe."""
from pathlib import Path

import cv2
from edge_impulse_linux.image import ImageImpulseRunner

DEFAULT_MODEL = str(Path.home() / "effaroucheur-perruches/unoq/models/perruche.eim")


class PerrucheDetectorEIM:
    def __init__(self, model_path=DEFAULT_MODEL):
        self.runner = ImageImpulseRunner(model_path)
        info = self.runner.init()
        p = info["model_parameters"]
        self.width = p["image_input_width"]    # 128
        self.height = p["image_input_height"]  # 128
        self.labels = p["labels"]

    def predict(self, frame_bgr):
        """Retourne un dict {label: score} pour une image OpenCV (BGR)."""
        # squash (etirement) : c'est le redimensionnement utilise a l'entrainement
        resized = cv2.resize(frame_bgr, (self.width, self.height))
        features, _ = self.runner.get_features_from_image(resized)
        res = self.runner.classify(features)
        return res["result"]["classification"]

    def close(self):
        self.runner.stop()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()