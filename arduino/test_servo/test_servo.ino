// ТЕСТ сервопривода: качается без остановки 0° -> 90° -> 180° -> 90° -> 0°.
// Подключение напрямую к Arduino, без макетной платы:
//   коричневый -> GND, красный -> 5V, оранжевый -> пин 3
#include <Servo.h>
Servo s;

void setup() {
  Serial.begin(9600);
  s.attach(3);
}

void loop() {
  s.write(0);   Serial.println("0");   delay(1500);
  s.write(90);  Serial.println("90");  delay(1500);
  s.write(180); Serial.println("180"); delay(1500);
  s.write(90);  Serial.println("90");  delay(1500);
}
