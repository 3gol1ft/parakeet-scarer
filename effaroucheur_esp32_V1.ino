/*
 * Recepteur BLE pour le systeme d'effarouchement de perruches.
 * Attend l'octet 0x01 sur la caracteristique BLE 0000ffe1-..., puis joue
 * un son aleatoire non repete via le DFPlayer Mini sur la carte SD.
 */
#include <HardwareSerial.h>
#include <DFRobotDFPlayerMini.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>

#define RX_PIN 16          // ESP32 RX  <- DFPlayer TX
#define TX_PIN 17          // ESP32 TX  -> DFPlayer RX
#define VOLUME 25          // 0..30
#define NB_SONS_DEFAUT 3   // secours si la lecture du nombre echoue

#define NOM_BLE             "EFFAROUCHEUR_ESP32"
#define SERVICE_UUID        "0000ffe0-0000-1000-8000-00805f9b34fb"
#define CHARACTERISTIC_UUID "0000ffe1-0000-1000-8000-00805f9b34fb"

HardwareSerial dfSerial(2);
DFRobotDFPlayerMini dfplayer;

int nbSons = 0;
int dernierSon = -1;
volatile bool declencher = false;

class ServerCB : public BLEServerCallbacks {
  void onConnect(BLEServer *s) override { Serial.println("[BLE] UNO Q connecte"); }
  void onDisconnect(BLEServer *s) override {
    Serial.println("[BLE] UNO Q deconnecte -> remise en attente");
    BLEDevice::startAdvertising();
  }
};

class CmdCB : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *c) override { declencher = true; }
};

void jouerSonAleatoire() {
  int choix;
  do { choix = random(1, nbSons + 1); } while (nbSons > 1 && choix == dernierSon);
  dernierSon = choix;
  Serial.printf("[SON] lecture du son %d / %d\n", choix, nbSons);
  dfplayer.play(choix);
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("Effaroucheur ESP32 demarre.");

  randomSeed(analogRead(34));

  dfSerial.begin(9600, SERIAL_8N1, RX_PIN, TX_PIN);
  if (!dfplayer.begin(dfSerial)) {
    Serial.println("[DFPLAYER] NON detecte ! Verifie cablage + carte SD.");
  }
  delay(1000);
  dfplayer.setTimeOut(800);
  dfplayer.volume(VOLUME);

  for (int i = 0; i < 5 && nbSons <= 0; i++) { nbSons = dfplayer.readFileCounts(); delay(400); }
  if (nbSons <= 0) nbSons = NB_SONS_DEFAUT;
  Serial.printf("[DFPLAYER] %d sons detectes sur la SD\n", nbSons);

  BLEDevice::init(NOM_BLE);
  BLEServer *serveur = BLEDevice::createServer();
  serveur->setCallbacks(new ServerCB());
  BLEService *service = serveur->createService(SERVICE_UUID);
  BLECharacteristic *carac = service->createCharacteristic(
      CHARACTERISTIC_UUID,
      BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
  carac->setCallbacks(new CmdCB());
  service->start();
  BLEDevice::getAdvertising()->addServiceUUID(SERVICE_UUID);
  BLEDevice::startAdvertising();
  Serial.println("[BLE] En attente de connexion (EFFAROUCHEUR_ESP32)...");
}

void loop() {
  if (declencher) {
    declencher = false;
    jouerSonAleatoire();
  }
}