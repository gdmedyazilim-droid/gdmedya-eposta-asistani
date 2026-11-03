"""ortam.py — Yollar, master.env okuma ve günlük (log) yazımı.

Diğer modüller buradan beslenir; dışarıya bağımlılığı yoktur.
"""
import datetime
import os
import sys

KOK = os.path.dirname(os.path.abspath(__file__))
ANTIGRAVITY = os.path.abspath(os.path.join(KOK, "..", ".."))
CRED_DIR = os.path.join(ANTIGRAVITY, "_knowledge", "credentials")
OAUTH_DIR = os.path.join(CRED_DIR, "oauth")
MASTER_ENV = os.path.join(CRED_DIR, "master.env")


def env_yukle(yol=MASTER_ENV):
    """master.env içindeki KEY=VALUE satırlarını ortam değişkenine yükler.

    Zaten tanımlı olan değişkenin üzerine yazmaz (sistem ortamı kazanır).
    """
    if not os.path.exists(yol):
        return False
    with open(yol, encoding="utf-8-sig") as f:
        for satir in f:
            satir = satir.strip()
            if not satir or satir.startswith("#") or "=" not in satir:
                continue
            anahtar, deger = satir.split("=", 1)
            anahtar = anahtar.strip()
            deger = deger.strip().strip('"').strip("'")
            if anahtar and anahtar not in os.environ:
                os.environ[anahtar] = deger
    return True


def gercek_deger(ad):
    """Ortam değişkenini döndürür; boşsa veya '<YER_TUTUCU>' ise None."""
    deger = os.environ.get(ad, "").strip()
    if not deger or deger.startswith("<"):
        return None
    return deger


def konsolu_hazirla():
    """Windows konsolunda Türkçe karakter ve emoji yüzünden çökmeyi önler."""
    for akis in (sys.stdout, sys.stderr):
        if akis is not None and hasattr(akis, "reconfigure"):
            try:
                akis.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


class Gunluk:
    """Hem ekrana (varsa) hem dosyaya yazan basit günlük.

    Görev Zamanlayıcı pythonw.exe ile çalıştırdığında sys.stdout None olur;
    o durumda yalnız dosyaya yazılır.
    """

    def __init__(self, dosya=None):
        self.dosya = dosya
        if dosya:
            os.makedirs(os.path.dirname(dosya), exist_ok=True)

    def __call__(self, mesaj=""):
        if sys.stdout is not None:
            try:
                print(mesaj, flush=True)
            except Exception:
                pass
        if self.dosya:
            zaman = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(self.dosya, "a", encoding="utf-8") as f:
                f.write("[{}] {}\n".format(zaman, mesaj))

