// Модуль 6. Пожарная сигнализация
const int FLAME = 2;     // DO датчика: при огне LOW
const int LED = 5;
const int BUZZER = 8;

void setup() {
  pinMode(FLAME, INPUT);
  pinMode(LED, OUTPUT);
  pinMode(BUZZER, OUTPUT);
  Serial.begin(9600);
}

void loop() {
  if (digitalRead(FLAME) == LOW) {        // огонь!
    Serial.println("ПОЖАР!");
    digitalWrite(LED, HIGH);
    tone(BUZZER, 1500);                    // сирена: высокий звук
    delay(250);
    digitalWrite(LED, LOW);
    tone(BUZZER, 900);                     // низкий звук
    delay(250);
  } else {
    noTone(BUZZER);
    digitalWrite(LED, LOW);
    delay(50);
  }
}
