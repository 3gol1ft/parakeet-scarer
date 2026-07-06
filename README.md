# Parakeet-Scarer
Un effaroucheur de perruches doté d'intelligence artificielle : il se compose de trois modules. Le premier module comprend un Arduino Uno Q et une caméra servant à détecter les perruches. Les deux autres modules sont un moteur et un haut-parleur qui communiquent avec le module 1 via des ESP32 utilisant la technologie BLE.

Contexte : Journée des projets E3E de l'ESIEE PARIS en 2026

<img width="1776" height="890" alt="image" src="https://github.com/user-attachments/assets/6ec508c8-42a0-458c-a27d-8708ca8dced9" />
<img width="1787" height="1003" alt="image" src="https://github.com/user-attachments/assets/cb13827e-9103-4bed-b343-9bf648d20b95" />

# Effaroucheur de perruches — Documentation complète

Système automatique de détection et d'effarouchement de perruches à collier,
basé sur une caméra, un modèle d'IA embarqué et un module son sans fil.

---

## Table des matières

1. [Introduction — à quoi ça sert et comment ça marche](#1-introduction)
2. [Liste du matériel](#2-liste-du-matériel)
3. [Branchements](#3-branchements)
4. [Structure des fichiers](#4-structure-des-fichiers)
5. [Bibliothèques et composants logiciels](#5-bibliothèques-et-composants-logiciels)
6. [L'IA : modèle, inférence et anti-faux-positifs](#6-lia--modèle-inférence-et-anti-faux-positifs)
7. [Configuration](#7-configuration)
8. [Commandes utiles](#8-commandes-utiles)
9. [Le service systemd](#9-le-service-systemd)
10. [Le dashboard web](#10-le-dashboard-web)

---

## 1. Introduction

### À quoi ça sert ?

Les perruches à collier (espèce invasive) causent des dégâts importants sur les cultures et les jardins. Ce système les détecte automatiquement grâce à une caméra et un modèle d'intelligence artificielle, puis déclenche un son d'effarouchement (cri de prédateur, bruit fort) pour les faire fuir — sans intervention humaine.

### Pourquoi ce design ?

- **Pas de WiFi sur site** : la communication entre la carte principale et le module son se fait en Bluetooth Low Energy (BLE), qui ne nécessite aucune infrastructure réseau.
- **IA embarquée** : le modèle tourne entièrement en local sur la carte Arduino UNO Q (pas de cloud, pas de latence réseau).
- **Autonomie** : le système démarre tout seul à l'alimentation grâce à un service systemd, et se reconnecte automatiquement si le BLE est perdu.

### Flux de fonctionnement

```
[Webcam C920] --USB--> [Arduino UNO Q]
                              |
                    capture une image
                              |
                    redimensionne en 128x128
                              |
                    modele IA Edge Impulse
                    (classification : perruche / pas_perruche)
                              |
                    score de confiance (0.0 -> 1.0)
                              |
                    filtre anti-faux-positifs
                    (seuil + fenetre temporelle + hysteresis)
                              |
                   detecte ? OUI -----------------------> [photo sauvegardee]
                              |                           [ligne dans journal.csv]
                              |
                    cooldown ecoule ? OUI
                              |
                    envoi BLE (octet 0x01)
                              |
                         [ESP32] --UART--> [DFPlayer Mini] --> [Haut-parleur]
                                                 |
                                         joue un son aleatoire
                                         depuis la carte SD
```

---

## 2. Liste du matériel

| Composant | Rôle |
|---|---|
| Arduino UNO Q (Qualcomm QRB2210) | Cerveau : IA, dashboard web, BLE client |
| Webcam Logitech C920 | Capture vidéo 1280×720 via USB |
| Hub USB | Concentrateur USB sur l'UNO Q |
| ESP32 Dev Module | Module son : serveur BLE + lecture SD |
| DFPlayer Mini | Lecteur MP3 piloté par UART |
| Carte microSD (≥ 2 Go) | Stockage des ~121 sons (~15 s chacun) |
| Haut-parleur 4Ω ou 8Ω | Diffusion du son d'effarouchement |
| Résistance 1 kΩ | Protection sur la liaison UART RX |
| Alimentation 5 V | Pour l'ESP32 et le DFPlayer |

---

## 3. Branchements

### Côté Arduino UNO Q

```
UNO Q (port USB)
    └── Hub USB
            ├── Webcam Logitech C920
            └── (autres périphériques USB si besoin)
```

La carte UNO Q communique avec l'ESP32 uniquement en **BLE** (sans fil). Aucun câble entre eux.

### Câblage ESP32 ↔ DFPlayer Mini

```
ESP32 Dev Module          DFPlayer Mini
─────────────────         ─────────────
5V (VIN)         ──────── VCC
GND              ──────── GND
GPIO17 (TX2)     ──[1kΩ]── RX
GPIO16 (RX2)     ──────── TX
                           SPK_1 ──── Haut-parleur (+)
                           SPK_2 ──── Haut-parleur (-)
```

> **Pourquoi la résistance 1 kΩ sur RX ?**
> Le DFPlayer Mini fonctionne en logique 3,3 V mais son entrée RX tolère mal les 3,3 V directs de l'ESP32 à pleine vitesse. La résistance limite le courant et évite les corruptions de commande.

### Carte microSD

Les fichiers sons doivent être nommés **0001.mp3, 0002.mp3, …, 0121.mp3** à la racine de la carte. Le DFPlayer les adresse par numéro (1 à N). La carte SD doit être formatée en **FAT32**.

### BLE (sans fil)

```
Arduino UNO Q (client BLE)  <--BLE-->  ESP32 (serveur BLE)
   Service UUID  : 0000ffe0-0000-1000-8000-00805f9b34fb
   Carac. UUID   : 0000ffe1-0000-1000-8000-00805f9b34fb
   Commande      : écriture de l'octet 0x01
```

---


## 4. Structure des fichiers

```
effaroucheur-perruches/
├── esp32/
│   └── effaroucheur_esp32/
│       └── effaroucheur_esp32_V1.ino   ← code Arduino/ESP32 (téléverser avec l'IDE Arduino)
└── unoq/
    ├── config.yaml                      ← SOURCE UNIQUE des réglages (modifier ici)
    ├── models/
    │   └── perruche.eim                 ← modèle Edge Impulse compilé (~16 Mo)
    ├── src/
    │   ├── web_demo.py                  ← PROGRAMME PRINCIPAL (lancé par systemd)
    │   ├── camera.py                    ← accès à la webcam
    │   ├── detector_eim.py              ← inférence IA
    │   ├── decision.py                  ← filtre anti-faux-positifs
    │   ├── ble_client.py                ← client BLE
    │   ├── journal.py                   ← journal CSV
    │   ├── config.py                    ← chargement de config.yaml
    │   └── main.py                      ← version console sans dashboard (debug)
    ├── tools/
    │   ├── capture_detections.py        ← test : capture avec filtre, sans son
    │   ├── test_camera.py               ← test : mesure FPS et photo de contrôle
    │   ├── test_detection.py            ← test : score en direct sans filtrage
    │   └── inspect_eim.py               ← affiche les paramètres du modèle .eim
    └── tests_data/
        ├── journal.csv                  ← journal réel des détections
        └── detections/                  ← photos horodatées des détections confirmées
```

---

## 5. Bibliothèques et composants logiciels

### Côté Arduino UNO Q (Python dans un venv)

| Bibliothèque | Rôle | Pourquoi ce choix |
|---|---|---|
| **OpenCV** (`cv2`) | Capture vidéo et encodage JPEG | Standard de facto pour la vision en Python |
| **edge-impulse-linux** | Chargement et exécution du modèle `.eim` | SDK officiel Edge Impulse pour Linux/ARM |
| **Flask** | Serveur HTTP du dashboard | Léger, sans dépendances lourdes |
| **bleak** | Client BLE asynchrone | Pure Python, multiplateforme, asyncio natif |
| **PyYAML** | Lecture de `config.yaml` | Simple, lisible, sans surcharge |
| **v4l2-ctl** (outil système) | Réglages de la caméra (focus, balance des blancs) | Contrôle fin des paramètres V4L2 depuis Python |

### Côté ESP32 (Arduino C++)

| Bibliothèque | Rôle |
|---|---|
| **BLEDevice / BLEServer** (ESP32 Arduino) | Serveur GATT BLE |
| **DFRobotDFPlayerMini** | Pilotage du DFPlayer Mini via UART |
| **HardwareSerial** | UART matériel sur GPIO16/17 |

---

## 6. L'IA : modèle, inférence et anti-faux-positifs
<img width="1787" height="1002" alt="image" src="https://github.com/user-attachments/assets/fb0eec30-1ec1-4e9d-8f8f-8824b0352862" />

### Le modèle Edge Impulse

Edge Impulse est une plateforme qui permet d'entraîner des modèles de machine learning directement sur des données récoltées, puis de les exporter sous forme d'un fichier `.eim` (binaire compilé pour l'architecture cible).

| Paramètre | Valeur |
|---|---|
| Format | `.eim` (binaire ARM64, Linux) |
| Type | Classification d'image entière |
| Entrée | 128 × 128 pixels, couleur RGB |
| Classes | `perruche`, `pas_perruche` |
| Temps d'inférence | ~126 ms par image |
| Cadence effective | ~6 à 7 images par seconde |

Le redimensionnement utilisé est le **squash** (étirement simple sans bandes noires) : c'est exactement la même transformation appliquée pendant l'entraînement, donc le modèle la reconnaît bien.

### Comment ça marche en pratique ?

Pour chaque image capturée, le modèle renvoie deux scores entre 0 et 1 dont la somme vaut 1 :

```
perruche      : 0.87
pas_perruche  : 0.13
```

On ne regarde que le score `perruche`. S'il dépasse le **seuil** (réglable dans `config.yaml`, actuellement **0.60**), l'image est considérée comme une détection candidate.

### La logique anti-faux-positifs

Une seule image ne suffit pas pour déclencher le son, car le modèle peut se tromper sur une image isolée (reflet, ombre, feuillage). Trois mécanismes se combinent pour fiabiliser la décision :

#### 1. Seuil par image (`seuil`)
Seules les images avec `score ≥ seuil` comptent comme « vue ». Réglé à **0.60**.

#### 2. Filtre temporel — fenêtre glissante (`n_requis` / `fenetre`)
On regarde les `fenetre` dernières images (actuellement **5**). Si au moins `n_requis` d'entre elles (actuellement **2**) ont passé le seuil → la perruche est **confirmée** et un événement est déclenché.

```
Exemple avec n_requis=2, fenetre=5 :

Images récentes : [0.82, 0.45, 0.71, 0.33, 0.22]
                     ✓      ✗     ✓     ✗     ✗
Résultat : 2 "vues" sur 5  → CONFIRMÉ (2 >= 2)
```

#### 3. Hystérésis — durée de présence (`n_perte`)
Une fois la perruche confirmée, elle reste "présente" même si le score plonge brièvement (oiseau qui tourne la tête, légère occultation). Elle n'est considérée "partie" qu'après `n_perte` images consécutives sous le seuil (actuellement **5**).

Cela évite de re-déclencher le son sur une même visite si la perruche reste dans le champ.

#### 4. Cooldown entre deux sons (`cooldown_s`)
Même si une nouvelle détection arrive, le son ne se redéclenche pas avant **17 secondes**. C'est légèrement supérieur à la durée des sons (~15 s) pour éviter les chevauchements sur l'ESP32.

### Récapitulatif des paramètres de décision

```yaml
detection:
  seuil: 0.60        # score minimum par image pour qu'elle "compte"
  n_requis: 2        # nombre de "vues" nécessaires sur la fenêtre
  fenetre: 5         # taille de la fenêtre glissante (en images)
  n_perte: 5         # images consécutives sous le seuil pour perdre la détection
  cooldown_s: 17.0   # délai minimum entre deux sons
```

---

## 7. Configuration

Tout se règle dans **`unoq/config.yaml`** — c'est la seule source de vérité. Aucun réglage n'est codé en dur dans les scripts.

```yaml
detection:
  seuil: 0.60        # baisser = plus sensible (plus de faux positifs)
  n_requis: 2        # monter = plus strict (moins de faux positifs)
  fenetre: 5
  n_perte: 5
  cooldown_s: 17.0

camera:
  largeur: 1280
  hauteur: 720
  focus: 20          # mise au point fixe (0..250 selon la distance à l'arbre)

ble:
  nom: "EFFAROUCHEUR_ESP32"
  carac_uuid: "0000ffe1-0000-1000-8000-00805f9b34fb"

web:
  port: 5000

horaires:
  debut_nuit: 21   # heure d'extinction de la caméra (BLE reste actif)
  fin_nuit: 6      # heure de reprise

chemins:
  detections: "~/effaroucheur-perruches/unoq/tests_data/detections"
  journal: "~/effaroucheur-perruches/unoq/tests_data/journal.csv"
```

---

## 8. Commandes utiles

### Après chaque upload depuis Windows

Quand vous copiez le dossier depuis Windows via VSCode Remote SSH, les bits d'exécution Linux sont perdus. Lancez ce script une fois après chaque upload :

```bash
bash ~/effaroucheur-perruches/deploy.sh
```

Il remet les permissions sur Python, le venv et le modèle `.eim`, redémarre le service systemd, affiche son statut, et affiche l'URL du dashboard.

### Trouver l'adresse IP de la carte UNO Q

```bash
hostname -I
```

Le dashboard web est ensuite accessible depuis n'importe quel appareil sur le même réseau à l'adresse :

```
http://<IP>:5000
```

### Lancer le programme manuellement (mode dashboard)

```bash
cd ~/effaroucheur-perruches/unoq
source .venv/bin/activate
python src/web_demo.py
```

### Lancer en mode console (sans dashboard, pour déboguer)

```bash
cd ~/effaroucheur-perruches/unoq
source .venv/bin/activate
python src/main.py
```

### Outils de test (sans déclencher le son)

```bash
# Test caméra : mesure FPS et enregistre une photo
python tools/test_camera.py

# Voir le score de détection en direct (pas de filtre, pas de son)
python tools/test_detection.py

# Voir ce que lit le modèle (taille d'entrée, classes, paramètres)
python tools/inspect_eim.py

# Capturer les détections confirmées (avec filtre, sans son)
python tools/capture_detections.py
```

---

## 9. Le service systemd

Le programme se lance **automatiquement au démarrage** de la carte grâce au service `effaroucheur.service`.

### Commandes essentielles

```bash
# Voir l'état du service (tourne ? erreur ?)
sudo systemctl status effaroucheur

# Arrêter le programme (libère la caméra et le BLE)
sudo systemctl stop effaroucheur

# Redémarrer après une modification
sudo systemctl restart effaroucheur

# Désactiver le démarrage automatique (pour travailler sans qu'il se relance)
sudo systemctl disable effaroucheur

# Réactiver le démarrage automatique
sudo systemctl enable effaroucheur

# Suivre les logs en direct
sudo journalctl -u effaroucheur -f

# Voir les derniers logs (50 lignes)
sudo journalctl -u effaroucheur -n 50
```

> **Important :** si vous voulez lancer `web_demo.py` à la main, arrêtez d'abord le service (`stop`), sinon la caméra sera déjà occupée et le second processus échouera.

### Localisation du fichier service

Le fichier de configuration systemd se trouve normalement à :

```
/etc/systemd/system/effaroucheur.service
```

Exemple de contenu typique :

```ini
[Unit]
Description=Effaroucheur de perruches
After=network.target

[Service]
ExecStart=/home/user/effaroucheur-perruches/unoq/.venv/bin/python /home/user/effaroucheur-perruches/unoq/src/web_demo.py
WorkingDirectory=/home/user/effaroucheur-perruches/unoq
Restart=always
User=user

[Install]
WantedBy=multi-user.target
```

---

## 10. Le dashboard web

Une fois le programme lancé, ouvrez `http://<IP>:5000` dans un navigateur.
L'adresse est également affichée dans le terminal au démarrage.

<img width="277" height="312" alt="image" src="https://github.com/user-attachments/assets/5d9feaba-5fd1-4149-9f64-5a3e7aa932bc" />


- **Bannière gradient** : la couleur passe du vert au jaune puis au rouge selon le score brut de l'IA (0.0 → vert, 0.5 → jaune, 1.0 → rouge). Le texte indique l'état confirmé (`PERRUCHE detectee` / `Detection en cours...` / `Pas de perruche`). La même couleur est appliquée sur le rectangle en haut du flux vidéo et sur le chiffre du score.
- **Infos système** : CPU, RAM, température du processeur, mode jour/nuit.
- **Graphe** : historique du score sur les 80 dernières images, ligne pointillée = seuil actif.
- **Alertes** : le bouton "Alertes : ON/OFF" active un bip sonore (Web Audio API) et un flash du titre de l'onglet à chaque nouvelle détection. Fonctionne sur tous les navigateurs en HTTP sans permission requise.
- **Mode nuit manuel** : le bouton change selon la situation — "Forcer mode nuit" (pendant la journée), "Forcer mode jour (tests)" (la nuit, pour tester sans attendre le matin), ou "reprendre" pour revenir en automatique. Le BLE reste toujours actif quelle que soit la position.
- **Dernière détection** : photo capturée lors de la dernière détection confirmée.
- **Tableau** : les 10 dernières lignes du journal CSV, rechargées toutes les 10 secondes.

### Mode nuit

Entre `debut_nuit` et `fin_nuit` (réglables dans `config.yaml`), la caméra s'éteint et l'inférence s'arrête. Le thread BLE reste actif toute la nuit — l'ESP32 n'a pas besoin d'être redémarré. La caméra se rallume automatiquement à l'heure configurée.

### Photos et journal

Les photos des détections sont sauvegardées dans `tests_data/detections/` :
```
2026-06-17_20-01-03_perruche_0.63.jpg
```
Chaque détection est consignée dans `tests_data/journal.csv` :
```
horodatage,score,son_joue
2026-06-17 20:01:03,0.628,1
```

### Dépendances supplémentaires

`psutil` est nécessaire pour l'affichage CPU/RAM. À installer une fois dans le venv :
```bash
source ~/effaroucheur-perruches/unoq/.venv/bin/activate
pip install psutil
```





<img width="1691" height="950" alt="image" src="https://github.com/user-attachments/assets/00706b2d-11a8-434d-ba58-4d021633ca16" />
L'alimentation n'a pas encore été travaillée, c'est une voie à explorer pour l'autonomie du projet 




---
# ANNEXES :
<img width="698" height="368" alt="image" src="https://github.com/user-attachments/assets/7a4f9b90-fe8d-4973-86ba-b67d554256a0" />
<img width="368" height="316" alt="image" src="https://github.com/user-attachments/assets/bd386ee6-b79c-49bc-b8f4-5dcc59cbf190" />

