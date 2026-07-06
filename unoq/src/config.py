"""Chargement de la configuration centrale (config.yaml).
Expose CFG (dict complet) et chemin() pour acceder aux chemins avec ~ etendu.
A importer par tous les modules Python du projet."""
from pathlib import Path

import yaml

_CHEMIN = Path(__file__).resolve().parent.parent / "config.yaml"

with open(_CHEMIN, "r", encoding="utf-8") as f:
    CFG = yaml.safe_load(f)


def chemin(cle):
    """Renvoie un chemin de la section 'chemins', avec ~ etendu."""
    return Path(CFG["chemins"][cle]).expanduser()
