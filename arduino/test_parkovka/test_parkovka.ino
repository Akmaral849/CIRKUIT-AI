// ТЕСТ модуля 2: проверяем отдельно сервопривод и датчик.
// 1) При включении сервопривод качается 0° -> 90° -> 0°.
// 2) Потом в Монитор порта (9600) каждые 0.3 с пишется расстояние.
#include <Servo.h>
const int TRIG = 9, ECHO = 10, SERVO_PIN = 3;
Servo s;

void setup() {
  Serial.begin(9600);
  pinMode(TRIG, OUTPUT);
  pinMode(ECHO, INPUT);
  s.attach(SERVO_PIN);
  Serial.println("Тест сервопривода: 0 -> 90 -> 0");
  s.write(0);  delay(1000);
  s.write(90); delay(1000);
  s.write(0);  delay(1000);
  Serial.println("Тест датчика: поднеси руку");
}

void loop() {
  digitalWrite(TRIG, LOW);  delayMicroseconds(2);
  digitalWrite(TRIG, HIGH); delayMicroseconds(10);
  digitalWrite(TRIG, LOW);
  long t = pulseIn(ECHO, HIGH, 30000);
  if (t == 0) Serial.println("Эхо НЕ вернулось (0) - проверь провода датчика");
  else { Serial.print("Расстояние: "); Serial.print(t / 58); Serial.println(" см"); }
  delay(300);
}
