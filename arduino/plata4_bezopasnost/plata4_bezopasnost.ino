// Плата 4 «Безопасность»: модуль 6 (пожарная сигнализация) + модуль 7 (охрана здания).
// Пожар: голый ИК-диод — A1 (встроенная подтяжка, вторая ножка к GND),
//        красный светодиод — пин 5, зуммер — пин 8.
// Охрана: зелёный светодиод-излучатель горит всегда (через резистор к 5V),
//         фоторезистор — A0 (встроенная подтяжка, вторая ножка к GND),
//         зелёный светодиод тревоги — пин 6, звук — тот же зуммер.
// После включения 2 секунды идёт калибровка: не подносить огонь и не перекрывать луч.
// Версия 18.11: раз в 0,5 с плата отправляет сайту строку CAI|... (самодиагностика по USB).

const int IR_PIN = A1;
const int FIRE_LED = 5;
const int BUZZER = 8;
const int BEAM = A0;
const int GUARD_LED = 6;

const int FIRE_DELTA = 30;   // на сколько должно УПАСТЬ число на A1 (среднее из 64), чтобы считать «огонь»
const int FIRE_NEED = 3;     // столько измерений подряд должно показать огонь — защита от случайных скачков
const int BEAM_DELTA = 100;  // насколько должно вырасти число на A0, когда луч перекрыт

float irBase = 0;            // обычное значение ИК-диода (без огня), медленно подстраивается под комнату
int fireCount = 0;
int limit = 1000;            // порог «луч перекрыт»
bool blocked = false;
int passes = 0;
unsigned long guardUntil = 0;
unsigned long lastBlink = 0;
unsigned long lastReport = 0;
bool blinkOn = false;
bool fireSeen = false;       // огонь был с прошлого отчёта

int readAvg(int pin) {        // среднее из 5 измерений, чтобы убрать дрожание
  long sum = 0;
  for (int i = 0; i < 5; i++) sum += analogRead(pin);
  return sum / 5;
}

float readFine(int pin) {     // среднее из 64 измерений: шум почти исчезает, видно даже маленькое падение
  long sum = 0;
  for (int i = 0; i < 64; i++) sum += analogRead(pin);
  return sum / 64.0;
}

void setup() {
  Serial.begin(9600);
  pinMode(IR_PIN, INPUT_PULLUP);
  pinMode(BEAM, INPUT_PULLUP);
  pinMode(FIRE_LED, OUTPUT);
  pinMode(GUARD_LED, OUTPUT);
  pinMode(BUZZER, OUTPUT);

  // Калибровка 2 секунды
  long irSum = 0, beamSum = 0;
  for (int i = 0; i < 40; i++) {
    irSum += analogRead(IR_PIN);
    beamSum += analogRead(BEAM);
    delay(50);
  }
  irBase = irSum / 40.0;
  int beam = beamSum / 40;
  limit = min(beam + BEAM_DELTA, 1000);
}

void loop() {
  // ---------- Модуль 6: пожар ----------
  float ir = readFine(IR_PIN);
  if (ir < irBase - FIRE_DELTA) fireCount++;   // огонь даёт ИК-излучение — число падает
  else { fireCount = 0; irBase = irBase * 0.997 + ir * 0.003; }   // без огня фон медленно подстраивается
  bool fire = fireCount >= FIRE_NEED;
  if (fire) {
    fireSeen = true;
    if (millis() - lastBlink > 250) {          // сирена: мигание и два тона
      lastBlink = millis();
      blinkOn = !blinkOn;
      digitalWrite(FIRE_LED, blinkOn ? HIGH : LOW);
      tone(BUZZER, blinkOn ? 1500 : 900);
    }
  } else {
    digitalWrite(FIRE_LED, LOW);
  }

  // ---------- Модуль 7: охрана ----------
  int v = readAvg(BEAM);                       // перекрыли луч — число растёт
  if (!blocked && v > limit) {
    blocked = true;
    passes++;
    guardUntil = millis() + 1500;
    if (!fire) tone(BUZZER, 2000, 300);
  }
  if (blocked && v < limit - 40) blocked = false;
  digitalWrite(GUARD_LED, millis() < guardUntil ? HIGH : LOW);

  if (!fire && millis() > guardUntil) noTone(BUZZER);

  // ---------- Отчёт сайту ----------
  if (millis() - lastReport > 500) {
    lastReport = millis();
    Serial.print("CAI|b=4|a1="); Serial.print(ir, 0);
    Serial.print("|base="); Serial.print(irBase, 0);
    Serial.print("|fire="); Serial.print(fireSeen ? 1 : 0);
    Serial.print("|a0="); Serial.print(v);
    Serial.print("|lim="); Serial.print(limit);
    Serial.print("|passes="); Serial.println(passes);
    fireSeen = false;
  }
  delay(20);
}
