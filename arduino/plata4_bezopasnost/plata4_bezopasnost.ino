// Плата 4 «Безопасность»: модуль 6 (пожарная сигнализация) + модуль 7 (охрана здания).
// Пожар: голый ИК-диод — A1 (встроенная подтяжка, вторая ножка к GND),
//        красный светодиод — пин 5, зуммер — пин 8.
// Охрана: зелёный светодиод-излучатель горит всегда (через резистор к 5V),
//         фоторезистор — A0 (встроенная подтяжка, вторая ножка к GND),
//         зелёный светодиод тревоги — пин 6, звук — тот же зуммер.
// После включения 2 секунды идёт калибровка: не подносить огонь и не перекрывать луч.

const int IR_PIN = A1;
const int FIRE_LED = 5;
const int BUZZER = 8;
const int BEAM = A0;
const int GUARD_LED = 6;

const int FIRE_DELTA = 60;   // насколько должно измениться число на A1, чтобы считать «огонь»
const int BEAM_DELTA = 100;  // насколько должно вырасти число на A0, когда луч перекрыт

int irBase = 0;              // обычное значение ИК-диода (без огня)
int limit = 1000;            // порог «луч перекрыт»
bool blocked = false;
int passes = 0;
unsigned long guardUntil = 0;
unsigned long lastBlink = 0;
unsigned long lastPrint = 0;
bool blinkOn = false;

int readAvg(int pin) {        // среднее из 5 измерений, чтобы убрать дрожание
  long sum = 0;
  for (int i = 0; i < 5; i++) sum += analogRead(pin);
  return sum / 5;
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
  irBase = irSum / 40;
  int beam = beamSum / 40;
  limit = min(beam + BEAM_DELTA, 1000);

  Serial.print("Пожар: обычное значение A1 = "); Serial.println(irBase);
  Serial.print("Охрана: луч A0 = "); Serial.print(beam);
  Serial.print(", тревога выше "); Serial.println(limit);
  if (beam > 900) Serial.println("ВНИМАНИЕ: луч слабый. Проверь, что излучатель горит и светит прямо в фоторезистор.");
}

void loop() {
  // ---------- Модуль 6: пожар ----------
  int ir = readAvg(IR_PIN);
  bool fire = abs(ir - irBase) > FIRE_DELTA;
  if (fire) {
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
    Serial.print("Охрана: проход! Всего: "); Serial.println(passes);
    if (!fire) tone(BUZZER, 2000, 300);
  }
  if (blocked && v < limit - 40) blocked = false;
  digitalWrite(GUARD_LED, millis() < guardUntil ? HIGH : LOW);

  if (!fire && millis() > guardUntil) noTone(BUZZER);

  // Раз в секунду — числа в монитор порта (для проверки и защиты)
  if (millis() - lastPrint > 1000) {
    lastPrint = millis();
    Serial.print("A1 (ИК) = "); Serial.print(ir);
    Serial.print(fire ? "  ПОЖАР!" : "  норма");
    Serial.print(" | A0 (луч) = "); Serial.println(v);
  }
  delay(20);
}
