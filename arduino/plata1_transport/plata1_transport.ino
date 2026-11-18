// Плата 1 «Транспорт»: модуль 1 (умный перекрёсток) + модуль 2 (умная парковка) вместе.
// Перекрёсток: светодиоды 4, 5, 6, кнопка 2, зуммер 8.
// Парковка: HC-SR04 Trig 9, Echo 10, сервопривод 3.
// Версия 18.11: раз в 0,5 с плата отправляет сайту строку CAI|... с измерениями (самодиагностика по USB).
#include <Servo.h>

// ---------- Модуль 1 ----------
const int RED = 4, YELLOW = 5, GREEN = 6;
const int BUTTON = 2;
const int BUZZER = 8;
bool pedestrian = false;

// ---------- Модуль 2 ----------
const int TRIG = 9, ECHO = 10;
const int SERVO_PIN = 3;
const int OPEN_CM = 10;           // ближе — машина у въезда
const int CLOSE_CM = 15;          // дальше — машины нет (гистерезис, чтобы не дёргался)
const int NEED = 3;               // столько измерений подряд нужно для решения
const unsigned long HOLD = 2000;  // ждём 2 с без машины, потом опускаем
int nearCount = 0, farCount = 0;
Servo barrier;
bool isOpen = false;
unsigned long lastSeen = 0;
unsigned long lastMeasure = 0;

// ---------- Самодиагностика ----------
long lastCm = -1;        // последнее расстояние, -1 — датчик не ответил
int missCount = 0;       // сколько измерений подряд датчик молчит
bool btnSeen = false;    // кнопку нажимали с прошлого отчёта
unsigned long lastReport = 0;

long distanceCm() {
  digitalWrite(TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG, LOW);
  // 45 мс: даже когда впереди пусто, исправный HC-SR04 отвечает импульсом ~38 мс.
  // 0 значит, что датчик вообще не ответил (нет провода, перепутаны Trig/Echo, нет питания).
  long t = pulseIn(ECHO, HIGH, 45000);
  if (t == 0) { missCount++; lastCm = -1; return 999; }
  missCount = 0;
  lastCm = t / 58;
  return lastCm;
}

void report() {
  if (millis() - lastReport < 500) return;
  lastReport = millis();
  Serial.print("CAI|b=1|btn="); Serial.print(btnSeen ? 1 : 0);
  Serial.print("|cm="); Serial.print(lastCm);
  Serial.print("|miss="); Serial.print(missCount);
  Serial.print("|open="); Serial.println(isOpen ? 1 : 0);
  btnSeen = false;
}

// Парковка проверяется раз в 60 мс, пока перекрёсток ждёт
void parkingTick() {
  if (millis() - lastMeasure < 60) return;
  lastMeasure = millis();
  long d = distanceCm();
  if (d < 2) return;                       // ошибка измерения — пропускаем

  // Фильтр: решение только если 3 измерения подряд говорят одно и то же
  if (d < OPEN_CM) { nearCount++; farCount = 0; }
  else if (d > CLOSE_CM) { farCount++; nearCount = 0; }
  else { nearCount = 0; farCount = 0; }   // зона 10–15 см: ничего не меняем

  if (nearCount >= NEED) {
    lastSeen = millis();
    if (!isOpen) { barrier.write(90); isOpen = true; }
  } else if (isOpen && farCount >= NEED && millis() - lastSeen > HOLD) {
    barrier.write(0);
    isOpen = false;
  }
}

// Ждём нужное время: следим за кнопкой, обслуживаем парковку и отчитываемся сайту
void waitAndWatch(unsigned long ms) {
  unsigned long start = millis();
  while (millis() - start < ms) {
    if (digitalRead(BUTTON) == LOW) { pedestrian = true; btnSeen = true; }
    parkingTick();
    report();
    delay(5);
  }
}

void light(int r, int y, int g) {
  digitalWrite(RED, r);
  digitalWrite(YELLOW, y);
  digitalWrite(GREEN, g);
}

void setup() {
  pinMode(RED, OUTPUT);
  pinMode(YELLOW, OUTPUT);
  pinMode(GREEN, OUTPUT);
  pinMode(BUTTON, INPUT_PULLUP);
  pinMode(BUZZER, OUTPUT);
  pinMode(TRIG, OUTPUT);
  pinMode(ECHO, INPUT);
  barrier.attach(SERVO_PIN);
  barrier.write(0);
  Serial.begin(9600);
}

void loop() {
  light(LOW, LOW, HIGH);   // машинам зелёный
  waitAndWatch(3000);
  light(LOW, HIGH, LOW);   // жёлтый
  waitAndWatch(1000);
  light(HIGH, LOW, LOW);   // машинам красный

  if (pedestrian) {
    for (int i = 0; i < 10; i++) {
      tone(BUZZER, 1000, 150);
      waitAndWatch(500);
    }
    pedestrian = false;
  } else {
    waitAndWatch(3000);
  }
}
