"""Gestionnaire BLE multi-device : un seul event loop asyncio pour tous les ESP32.
Un scan unique trouve tous les appareils cibles, evitant les conflits d'adaptateur.
Expose trigger(nom) et is_connected(nom) utilisables depuis n'importe quel thread."""
import asyncio
import threading

from bleak import BleakScanner, BleakClient


class BLEGestionnaire:
    def __init__(self, carac_uuid):
        self.carac_uuid = carac_uuid
        self._loop = asyncio.new_event_loop()
        self._noms = set()
        self._clients = {}   # nom -> BleakClient
        self._connecte = {}  # nom -> bool
        self._en_cours = set()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def enregistrer(self, nom):
        self._noms.add(nom)
        self._clients[nom] = None
        self._connecte[nom] = False
        return self

    def start(self):
        self._thread.start()

    def _run(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._boucle())

    async def _boucle(self):
        while True:
            manquants = {n for n in self._noms if not self._connecte[n] and n not in self._en_cours}
            if manquants:
                try:
                    print(f"[BLE] Scan ({manquants})...", flush=True)
                    appareils = await BleakScanner.discover(timeout=8.0)
                    trouves = {d.name: d for d in appareils if d.name in manquants}
                    for nom, dev in trouves.items():
                        self._en_cours.add(nom)
                        asyncio.ensure_future(self._connecter(nom, dev))
                    non_trouves = manquants - set(trouves)
                    if non_trouves:
                        print(f"[BLE] Introuvable: {non_trouves}", flush=True)
                except Exception as e:
                    print(f"[BLE] Erreur scan: {e}", flush=True)
            await asyncio.sleep(10)

    async def _connecter(self, nom, dev):
        print(f"[BLE] Connexion a {nom}...", flush=True)
        try:
            async with BleakClient(dev) as client:
                self._clients[nom] = client
                self._connecte[nom] = True
                print(f"[BLE] Connecte a {nom}", flush=True)
                while client.is_connected:
                    await asyncio.sleep(1)
        except Exception as e:
            print(f"[BLE] Erreur {nom}: {e}", flush=True)
        finally:
            self._clients[nom] = None
            self._connecte[nom] = False
            self._en_cours.discard(nom)
            print(f"[BLE] Deconnecte de {nom}", flush=True)

    def is_connected(self, nom):
        return self._connecte.get(nom, False)

    def trigger(self, nom):
        """Envoie 0x01 a l'appareil nom. Renvoie True si envoye."""
        if not self.is_connected(nom):
            print(f"[BLE] {nom} pas connecte, ordre ignore.", flush=True)
            return False
        client = self._clients.get(nom)
        if client is None:
            return False
        fut = asyncio.run_coroutine_threadsafe(
            client.write_gatt_char(self.carac_uuid, b"\x01", response=False),
            self._loop,
        )
        try:
            fut.result(timeout=5)
            return True
        except Exception as e:
            print(f"[BLE] Echec envoi {nom}: {e}", flush=True)
            return False
