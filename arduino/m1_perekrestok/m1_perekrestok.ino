// Модуль 1. Умный перекрёсток
const int RED = 4, YELLOW = 5, GREEN = 6;
const int BUTTON = 2;
const int BUZZER = 8;

bool pedestrian = false;   // пешеход нажал кнопку

// Ждём нужное время и всё это время следим за кнопкой
void waitAndWatch(unsigned long ms) {
  unsigned long start = millis();
  while (millis() - start < ms) {
    if (digitalRead(BUTTON) == LOW) pedestrian = true;
    delay(10);
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
  Serial.begin(9600);
}

void loop() {
  light(LOW, LOW, HIGH);   // машинам зелёный
  waitAndWatch(3000);
  light(LOW, HIGH, LOW);   // жёлтый
  waitAndWatch(1000);
  light(HIGH, LOW, LOW);   // машинам красный

  if (pedestrian) {
    Serial.println("Пешеход переходит");
    for (int i = 0; i < 10; i++) {   // 5 секунд со звуком
      tone(BUZZER, 1000, 150);
      delay(500);
    }
    pedestrian = false;
  } else {
    waitAndWatch(3000);
  }
}
