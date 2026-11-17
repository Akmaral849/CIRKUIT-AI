// Модуль 5. Шумомер улицы
const int MIC = A0;
const int R = 9, G = 10, B = 11;
const int QUIET = 30;    // меньше — тихо (подбери по Монитору порта)
const int LOUD = 120;    // больше — громко

void color(int r, int g, int b) {
  analogWrite(R, r);
  analogWrite(G, g);
  analogWrite(B, b);
}

void setup() {
  pinMode(R, OUTPUT);
  pinMode(G, OUTPUT);
  pinMode(B, OUTPUT);
  Serial.begin(9600);
}

void loop() {
  // 50 мс читаем микрофон и ищем размах колебаний
  int lo = 1023, hi = 0;
  unsigned long start = millis();
  while (millis() - start < 50) {
    int v = analogRead(MIC);
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }
  int level = hi - lo;
  Serial.print("Громкость: ");
  Serial.println(level);

  if (level < QUIET) color(0, 255, 0);          // тихо — зелёный
  else if (level < LOUD) color(255, 120, 0);    // средне — жёлтый
  else { color(255, 0, 0); delay(500); }        // громко — красный, держим полсекунды
}
