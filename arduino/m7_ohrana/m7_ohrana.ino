// Модуль 7. Охрана здания (оптический барьер)
const int SENSOR = A0;
const int ALARM_LED = 6;
const int BUZZER = 8;      // зуммер общий с модулем 6

int beamLevel;             // значение, когда луч свободен
int limit;                 // больше этого — луч перекрыт
bool blocked = false;
int passes = 0;            // счётчик проходов

void setup() {
  pinMode(SENSOR, INPUT_PULLUP);
  pinMode(ALARM_LED, OUTPUT);
  pinMode(BUZZER, OUTPUT);
  Serial.begin(9600);

  long sum = 0;            // 2 секунды запоминаем свободный луч
  for (int i = 0; i < 40; i++) { sum += analogRead(SENSOR); delay(50); }
  beamLevel = sum / 40;
  limit = beamLevel + 100;
  Serial.print("Луч: "); Serial.println(beamLevel);
}

void loop() {
  int v = analogRead(SENSOR);   // перекрыли луч — число растёт

  if (!blocked && v > limit) {  // луч только что перекрыли
    blocked = true;
    passes++;
    Serial.print("Проход! Всего: "); Serial.println(passes);
    digitalWrite(ALARM_LED, HIGH);
    tone(BUZZER, 2000, 300);
  }
  if (blocked && v < limit - 40) {   // луч снова свободен
    blocked = false;
    digitalWrite(ALARM_LED, LOW);
  }
  delay(20);
}
