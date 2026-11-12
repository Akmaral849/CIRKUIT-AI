# Проверка: может ли Python достучаться до серверов Gemini.
# Запуск:  python net_test.py   (сам закроется максимум через 40 секунд)
import os
import socket
import ssl
import threading
import time
import urllib.request

HOST = "generativelanguage.googleapis.com"

# Сторож: что бы ни случилось, через 40 секунд программа закроется сама
threading.Timer(40, lambda: (print("\nСТОП: зависло больше 40 секунд."), os._exit(1))).start()

print("1) Прокси в системе:", urllib.request.getproxies() or "нет")

try:
    t = time.time()
    addrs = sorted({a[4][0] for a in socket.getaddrinfo(HOST, 443)})
    print(f"2) Адрес найден за {time.time() - t:.1f} с:", ", ".join(addrs[:4]))
except Exception as e:
    print("2) ОШИБКА: не нашёл адрес сервера (DNS):", e)
    os._exit(1)

for family, name in ((socket.AF_INET, "IPv4"), (socket.AF_INET6, "IPv6")):
    try:
        t = time.time()
        info = socket.getaddrinfo(HOST, 443, family)[0]
        s = socket.socket(family, socket.SOCK_STREAM)
        s.settimeout(8)
        s.connect(info[4])
        ctx = ssl.create_default_context()
        with ctx.wrap_socket(s, server_hostname=HOST) as tls:
            print(f"3) {name}: соединение есть ({time.time() - t:.1f} с)")
    except Exception as e:
        print(f"3) {name}: НЕТ соединения -> {type(e).__name__}: {str(e)[:80]}")

try:
    t = time.time()
    urllib.request.urlopen("https://" + HOST + "/", timeout=8)
    print(f"4) HTTPS-запрос прошёл за {time.time() - t:.1f} с")
except urllib.error.HTTPError as e:
    print(f"4) HTTPS-запрос прошёл (сервер ответил кодом {e.code}, это нормально) за {time.time() - t:.1f} с")
except Exception as e:
    print("4) HTTPS-запрос НЕ прошёл:", type(e).__name__, str(e)[:100])

print("\nГотово. Сделай скриншот и пришли Claude.")
os._exit(0)
