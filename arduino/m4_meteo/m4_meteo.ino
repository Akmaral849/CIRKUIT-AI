// Модуль 4. Метеостанция
// Библиотеки: «DHT sensor library» (Adafruit) и «hd44780» (Bill Perry).
// hd44780 сама находит адрес экрана (0x27 или 0x3F), менять в коде ничего не нужно.
#include <DHT.h>
#include <Wire.h>
#include <hd44780.h>
#include <hd44780ioClass/hd44780_I2Cexp.h>

DHT dht(2, DHT11);          // датчик на пине 2
hd44780_I2Cexp lcd;         // экран с платой I2C: SDA — A4, SCL — A5

void setup() {
  Serial.begin(9600);
  dht.begin();
  int status = lcd.begin(16, 2);
  if (status) {
    Serial.println("Экран не найден: проверь SDA (A4), SCL (A5), VCC и GND экрана");
  }
  lcd.print("Circuit AI");
  lcd.setCursor(0, 1);
  lcd.print("Meteostanciya");
  delay(2000);
}

void loop() {
  float t = dht.readTemperature();
  float h = dht.readHumidity();
  lcd.clear();

  if (isnan(t) || isnan(h)) {          // данные не пришли
    lcd.print("Oshibka datchika");
    Serial.println("Ошибка датчика DHT11");
  } else {
    lcd.print("Temp: ");
    lcd.print(t, 0);
    lcd.print(" C");
    lcd.setCursor(0, 1);
    lcd.print("Vlazh: ");
    lcd.print(h, 0);
    lcd.print(" %");
    Serial.print(t); Serial.print(" C  "); Serial.print(h); Serial.println(" %");
  }
  delay(2000);                          // DHT11 нельзя опрашивать чаще
}
