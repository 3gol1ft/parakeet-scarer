"""Inspection du modele Edge Impulse (.eim) : taille d'entree, classes et parametres complets.
Utile pour verifier qu'un nouveau modele est compatible avec le reste du systeme."""
import json
from pathlib import Path

from edge_impulse_linux.image import ImageImpulseRunner

MODEL = str(Path.home() / "effaroucheur-perruches/unoq/models/perruche.eim")


def main():
    runner = ImageImpulseRunner(MODEL)
    try:
        info = runner.init()
        params = info["model_parameters"]
        project = info.get("project", {})

        print("=== Projet ===")
        print(" ", project.get("owner"), "/", project.get("name"))

        print("\n=== Entrée attendue par le modèle ===")
        print("  taille    :", params.get("image_input_width"),
              "x", params.get("image_input_height"))
        print("  canaux    :", params.get("image_channel_count"),
              "(1 = niveaux de gris, 3 = couleur)")

        print("\n=== Type de modèle ===")
        print("  model_type:", params.get("model_type"))
        print("  classes   :", params.get("labels"))

        print("\n=== Détail complet (pour archive) ===")
        print(json.dumps(params, indent=2))
    finally:
        runner.stop()


if __name__ == "__main__":
    main()