// Модуль 3. Уличное освещение
const int SENSOR = A0;
const int LAMPS[] = {5, 6, 7};

int onLevel, offLevel;   // два порога: включить и выключить
bool lampsOn = false;

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
  if (room > 1000) {
    // 1023 значит, что на A0 нет делителя: фоторезистор не соединён с A0 или с GND
    Serial.println("ВНИМАНИЕ: A0 = 1023. Проверь провод A0 и провод фоторезистора к GND!");
  }
  onLevel = min(room + 150, 1000);   // заметно темнее — включаем (не выше 1000)
  offLevel = onLevel - 70;           // снова светлее — выключаем
  setLamps(false);
}
void loop() {
  int v = analogRead(SENSOR);     // чем темнее, тем больше число
  if (!lampsOn && v > onLevel) setLamps(true);
  if (lampsOn && v < offLevel) setLamps(false);

  Serial.print("Темнота: ");
  Serial.print(v);
  Serial.print("  порог: ");
  Serial.println(onLevel);
  delay(100);
}
