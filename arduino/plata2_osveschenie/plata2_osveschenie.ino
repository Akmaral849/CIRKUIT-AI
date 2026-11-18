// Плата 2: модуль 3 «Уличное освещение».
// Фоторезистор: одна ножка A0 (встроенная подтяжка), другая GND. Фонари: пины 5, 6, 7.
// Версия 18.11: раз в 0,3 с плата отправляет сайту строку CAI|... (самодиагностика по USB).
const int SENSOR = A0;
const int LAMPS[] = {5, 6, 7};

int onLevel, offLevel;   // два порога: включить и выключить
bool lampsOn = false;
unsigned long lastReport = 0;

void setLamps(bool on) {
  for (int i = 0; i < 3; i++) digitalWrite(LAMPS[i], on ? HIGH : LOW);
  lampsOn = on;
}

void setup() {
  pinMode(SENSOR, INPUT_PULLUP);   // встроенный резистор вместо внешнего
  for (int i = 0; i < 3; i++) pinMode(LAMPS[i], OUTPUT);
  Serial.begin(9600);

  // 2 секунды запоминаем свет в комнате
  long sum = 0;
  for (int i = 0; i < 40; i++) { sum += analogRead(SENSOR); delay(50); }
  int room = sum / 40;
  onLevel = min(room + 150, 1000);   // заметно темнее — включаем (не выше 1000)
  offLevel = onLevel - 70;           // снова светлее — выключаем
  setLamps(false);
}

void loop() {
  int v = analogRead(SENSOR);     // чем темнее, тем больше число; 1023 — фоторезистор не подключён
  if (!lampsOn && v > onLevel) setLamps(true);
  if (lampsOn && v < offLevel) setLamps(false);

  if (millis() - lastReport > 300) {
    lastReport = millis();
    Serial.print("CAI|b=2|a0="); Serial.print(v);
    Serial.print("|on="); Serial.print(onLevel);
    Serial.print("|lamps="); Serial.println(lampsOn ? 1 : 0);
  }
  delay(50);
}
