// Плата 3 «Экология»: модуль 4 (метеостанция) + модуль 5 (шумомер улицы).
// Метеостанция: DHT11 — пин 2; экран LCD 1602 с платой I2C — SDA A4, SCL A5.
// Шумомер: звуковой датчик AO — A0, G — GND, + — 5V (DO не используется);
//          RGB-светодиод: R — 9, G — 10, B — 11, общий — GND.
// Библиотеки: «DHT sensor library» (Adafruit) и «hd44780» (Bill Perry).
// После включения 2 секунды идёт калибровка тишины: не шуметь рядом с датчиком.
// Версия 19.11: раз в 0,5 с плата отправляет сайту строку CAI|b=3|... (самодиагностика по USB).
#include <DHT.h>
#include <Wire.h>
#include <hd44780.h>
#include <hd44780ioClass/hd44780_I2Cexp.h>

DHT dht(2, DHT11);
hd44780_I2Cexp lcd;

const int MIC = A0;
const int R = 9, G = 10, B = 11;

int quietBase = 0;      // среднее значение A0 в тишине
int quietSwing = 0;     // размах колебаний в тишине
int midLevel, loudLevel;
unsigned long redUntil = 0;

bool lcdOk = false;
bool dhtOk = false;
int tNow = 0, hNow = 0;
unsigned long lastDht = 0;

int peak = 0;           // самое большое значение A0 с прошлого отчёта
int maxSwing = 0;       // самый большой размах с прошлого отчёта
long sumLevel = 0;      // для среднего значения A0
int nLevel = 0;
unsigned long lastReport = 0;

void color(int r, int g, int b) {
  analogWrite(R, r);
  analogWrite(G, g);
  analogWrite(B, b);
}

bool lcdAnswers() {     // экран отвечает по шине I2C (адрес 0x27 или 0x3F)
  Wire.beginTransmission(0x27);
  if (Wire.endTransmission() == 0) return true;
  Wire.beginTransmission(0x3F);
  return Wire.endTransmission() == 0;
}

void readDht() {
  float t = dht.readTemperature();
  float h = dht.readHumidity();
  dhtOk = !(isnan(t) || isnan(h));
  if (dhtOk) { tNow = (int)(t + 0.5); hNow = (int)(h + 0.5); }

  lcdOk = lcdAnswers();
  if (!lcdOk) return;
  lcd.clear();
  if (!dhtOk) {
    lcd.print("Oshibka datchika");
  } else {
    lcd.print("Temp: "); lcd.print(tNow); lcd.print(" C");
    lcd.setCursor(0, 1);
    lcd.print("Vlazh: "); lcd.print(hNow); lcd.print(" %");
  }
}

void setup() {
  Serial.begin(9600);
  pinMode(R, OUTPUT); pinMode(G, OUTPUT); pinMode(B, OUTPUT);
  dht.begin();
  Wire.begin();
  Wire.setWireTimeout(3000, true);   // если провод экрана выдернут — плата не зависает
  lcdOk = (lcd.begin(16, 2) == 0);
  if (lcdOk) {
    lcd.print("Circuit AI");
    lcd.setCursor(0, 1);
    lcd.print("Ekologiya");
  }

  // Калибровка тишины 2 секунды
  long sum = 0; int n = 0; long swingSum = 0; int windows = 0;
  unsigned long start = millis();
  while (millis() - start < 2000) {
    int lo = 1023, hi = 0;
    unsigned long w = millis();
    while (millis() - w < 50) {
      int v = analogRead(MIC);
      if (v < lo) lo = v;
      if (v > hi) hi = v;
      sum += v; n++;
    }
    swingSum += hi - lo; windows++;
  }
  quietBase = sum / n;
  quietSwing = swingSum / windows;
  midLevel = quietSwing + 25;    // заметно громче тишины — жёлтый
  loudLevel = quietSwing + 60;   // хлопок — красный

  readDht();
  lastDht = millis();
}

void loop() {
  // ---------- Модуль 5: шумомер (50 мс слушаем микрофон) ----------
  int lo = 1023, hi = 0;
  unsigned long w = millis();
  while (millis() - w < 50) {
    int v = analogRead(MIC);
    if (v < lo) lo = v;
    if (v > hi) hi = v;
    sumLevel += v; nLevel++;
  }
  int swing = hi - lo;
  if (hi > peak) peak = hi;
  if (swing > maxSwing) maxSwing = swing;

  if (swing >= loudLevel) redUntil = millis() + 2000;   // хлопок: красный держим 2 с
  if (millis() < redUntil) color(255, 0, 0);
  else if (swing >= midLevel) color(255, 120, 0);      // средне — жёлтый
  else color(0, 255, 0);                               // тихо — зелёный

  // ---------- Модуль 4: метеостанция (DHT11 не чаще раза в 2 с) ----------
  if (millis() - lastDht > 2000) {
    lastDht = millis();
    readDht();
  }

  // ---------- Отчёт сайту ----------
  if (millis() - lastReport > 500) {
    lastReport = millis();
    int snd = nLevel ? sumLevel / nLevel : 0;
    Serial.print("CAI|b=3|lcd="); Serial.print(lcdOk ? 1 : 0);
    Serial.print("|dht="); Serial.print(dhtOk ? 1 : 0);
    Serial.print("|t="); Serial.print(tNow);
    Serial.print("|h="); Serial.print(hNow);
    Serial.print("|snd="); Serial.print(snd);
    Serial.print("|lvl="); Serial.print(maxSwing);
    Serial.print("|peak="); Serial.print(peak);
    Serial.print("|base="); Serial.println(quietBase);
    peak = 0; maxSwing = 0; sumLevel = 0; nLevel = 0;
  }
}
