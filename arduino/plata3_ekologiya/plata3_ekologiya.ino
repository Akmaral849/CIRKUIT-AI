// Плата 3 «Экология»: модуль 4 (метеостанция) + модуль 5 (шумомер).
// Метеостанция: DHT11 на пине 2, экран I2C (SDA — A4, SCL — A5).
// Шумомер: выход AO звукового датчика — A0 (аналоговый сигнал),
// RGB-модуль: R — 9, G — 10, B — 11.
#include <DHT.h>
#include <Wire.h>
#include <hd44780.h>
#include <hd44780ioClass/hd44780_I2Cexp.h>

DHT dht(2, DHT11);
hd44780_I2Cexp lcd;
unsigned long lastMeteo = 0;

const int MIC = A0;
const int R = 9, G = 10, B = 11;
int QUIET = 30, LOUD = 100;     // пороги считаются сами при включении
unsigned long redUntil = 0, lastPrint = 0;
int peak = 0, sMin = 1023, sMax = 0;   // для Монитора порта: размах, минимум и максимум за 1 с

void color(int r, int g, int b) { analogWrite(R, r); analogWrite(G, g); analogWrite(B, b); }

// Размах сигнала микрофона за 50 мс: чем громче, тем больше
int measureNoise() {
  int lo = 1023, hi = 0;
  unsigned long start = millis();
  while (millis() - start < 50) {
    int v = analogRead(MIC);
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }
  if (lo < sMin) sMin = lo;
  if (hi > sMax) sMax = hi;
  return hi - lo;
}

void calibrateNoise() {
  // 2 секунды слушаем тишину (не шуметь!)
  long sum = 0; int maxL = 0;
  for (int i = 0; i < 40; i++) { int l = measureNoise(); sum += l; if (l > maxL) maxL = l; }
  int base = sum / 40;
  QUIET = maxL + 5;
  LOUD = max(maxL + 25, base * 2);
  if (LOUD > 1000) LOUD = 1000;
  Serial.print("Шум: фон "); Serial.print(base);
  Serial.print(", тихо до "); Serial.print(QUIET);
  Serial.print(", громко от "); Serial.println(LOUD);
}

void noiseTick() {
  int level = measureNoise();
  if (level > peak) peak = level;
  if (millis() - lastPrint > 1000) {
    lastPrint = millis();
    Serial.print("Шум: размах "); Serial.print(peak);
    Serial.print("  (A0 от "); Serial.print(sMin); Serial.print(" до "); Serial.print(sMax);
    Serial.print(")  громко от "); Serial.println(LOUD);
    peak = 0; sMin = 1023; sMax = 0;
  }
  if (level >= LOUD) redUntil = millis() + 2000;   // держим красный 2 секунды
  if (millis() < redUntil) color(255, 0, 0);       // громко — красный
  else if (level < QUIET) color(0, 255, 0);        // тихо — зелёный
  else color(255, 120, 0);                         // средне — жёлтый
}

void meteoTick() {
  if (millis() - lastMeteo < 2000) return;
  lastMeteo = millis();
  float t = dht.readTemperature(), h = dht.readHumidity();
  lcd.clear();
  if (isnan(t) || isnan(h)) { lcd.print("Oshibka datchika"); return; }
  lcd.print("Temp: ");  lcd.print(t, 0); lcd.print(" C");
  lcd.setCursor(0, 1);
  lcd.print("Vlazh: "); lcd.print(h, 0); lcd.print(" %");
}

void setup() {
  Serial.begin(9600);
  pinMode(R, OUTPUT); pinMode(G, OUTPUT); pinMode(B, OUTPUT);
  dht.begin();
  if (lcd.begin(16, 2)) Serial.println("Экран не найден: проверь SDA (A4), SCL (A5), VCC и GND");
  lcd.print("Circuit AI");
  lcd.setCursor(0, 1);
  lcd.print("Ekologiya");
  calibrateNoise();
}

void loop() {
  noiseTick();
  meteoTick();
}
