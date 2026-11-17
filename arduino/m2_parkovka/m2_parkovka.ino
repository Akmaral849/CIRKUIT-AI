// Модуль 2. Умная парковка (с фильтром и гистерезисом)
#include <Servo.h>

const int TRIG = 9, ECHO = 10;
const int SERVO_PIN = 3;
const int OPEN_CM = 10;           // ближе — машина у въезда
const int CLOSE_CM = 15;          // дальше — машины нет (гистерезис)
const int NEED = 3;               // столько измерений подряд нужно для решения
const unsigned long HOLD = 2000;  // ждём 2 с без машины, потом опускаем

Servo barrier;
bool isOpen = false;
unsigned long lastSeen = 0, lastMove = 0;
int nearCount = 0, farCount = 0;

long distanceCm() {
  digitalWrite(TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG, LOW);
  long t = pulseIn(ECHO, HIGH, 30000);    // ждём эхо не дольше 30 мс
  if (t == 0) return 999;                 // эхо не вернулось
  return t / 58;
}

void setup() {
  pinMode(TRIG, OUTPUT);
  pinMode(ECHO, INPUT);
  barrier.attach(SERVO_PIN);
  barrier.write(0);                       // шлагбаум опущен
  Serial.begin(9600);
}

void loop() {
  delay(60);                              // пауза между измерениями по документации
  // 0.7 с после движения не меряем: мотор берёт много тока,
  // а шлагбаум может попасть в поле зрения датчика
  if (millis() - lastMove < 700) { nearCount = 0; farCount = 0; return; }

  long d = distanceCm();
  if (d < 2) return;                      // ошибка измерения — пропускаем

  if (d < OPEN_CM) { nearCount++; farCount = 0; }
  else if (d > CLOSE_CM) { farCount++; nearCount = 0; }
  else { nearCount = 0; farCount = 0; }  // зона 10–15 см: ничего не меняем

  if (nearCount >= NEED) {
    lastSeen = millis();
    if (!isOpen) { barrier.write(90); isOpen = true; lastMove = millis(); Serial.println("Шлагбаум поднят"); }
  } else if (isOpen && farCount >= NEED && millis() - lastSeen > HOLD) {
    barrier.write(0); isOpen = false; lastMove = millis(); Serial.println("Шлагбаум опущен");
  }
}
