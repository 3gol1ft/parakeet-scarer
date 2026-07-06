#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

#define MOTOR_PIN 26

#define SERVICE_UUID  "your service UUID"
#define CARAC_UUID    "your carac UUID"

volatile bool motorRequested = false;
bool deviceConnected = false;
BLEServer* pServer = nullptr;

class ServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer* pServer) {
    deviceConnected = true;
    Serial.println("[BLE] Client connecte");
  }
  void onDisconnect(BLEServer* pServer) {
    deviceConnected = false;
    Serial.println("[BLE] Deconnecte");
    pServer->startAdvertising();
  }
};

class MotorCallback : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic* pCarac) {
    uint8_t* data = pCarac->getData();
    size_t len = pCarac->getLength();
    if (len > 0) {
      Serial.print("[BLE] Recu : 0x");
      Serial.println(data[0], HEX);
      if (data[0] == 0x01) {
        motorRequested = true;
        Serial.println("[BLE] Moteur demande !");
      }
    }
  }
};

void setup() {
  Serial.begin(115200);
  pinMode(MOTOR_PIN, OUTPUT);
  digitalWrite(MOTOR_PIN, LOW);

  BLEDevice::init("EFFAROUCHEUR_MOTEUR");
  pServer = BLEDevice::createServer();
  pServer->setCallbacks(new ServerCallbacks());

  BLEService* pService = pServer->createService(SERVICE_UUID);
  BLECharacteristic* pCarac = pService->createCharacteristic(
    CARAC_UUID,
    BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR
  );
  pCarac->setCallbacks(new MotorCallback());
  pService->start();

  BLEAdvertising* pAdv = BLEDevice::getAdvertising();
  pAdv->addServiceUUID(SERVICE_UUID);
  pAdv->setScanResponse(true);
  pAdv->start();

  Serial.println("[ESP32] Pret - en attente BLE (EFFAROUCHEUR_MOTEUR)...");
}

void loop() {
  if (motorRequested) {
    motorRequested = false;
    Serial.println("[MOTEUR] ON 3 secondes");
    digitalWrite(MOTOR_PIN, HIGH);
    delay(3000);
    digitalWrite(MOTOR_PIN, LOW);
    Serial.println("[MOTEUR] OFF");
  }
}
