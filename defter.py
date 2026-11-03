"""defter.py — İşlenen maillerin JSONL kaydı.

Aynı mail ikinci kez işlenmez (örneğin YANIT_GEREKLI mail okunmamış kalır ve
ertesi gün tekrar listelenir; defter sayesinde ikinci bir taslak yazılmaz).
"""
import datetime
import json
import os


class Defter:
    def __init__(self, dosya):
        self.dosya = dosya
        self._gorulen = set()
        if dosya and os.path.exists(dosya):
            with open(dosya, encoding="utf-8") as f:
                for satir in f:
                    satir = satir.strip()
                    if not satir:
                        continue
                    try:
                        self._gorulen.add(json.loads(satir)["mail_id"])
                    except (ValueError, KeyError):
                        continue

    def var_mi(self, mail_id):
        return mail_id in self._gorulen

    def yaz(self, mail, kategori, aksiyon, neden, ek=None):
        self._gorulen.add(mail.id)
        if not self.dosya:
            return
        os.makedirs(os.path.dirname(self.dosya), exist_ok=True)
        kayit = {
            "zaman": datetime.datetime.now().isoformat(timespec="seconds"),
            "mail_id": mail.id,
            "thread_id": mail.thread_id,
            "gonderen": mail.gonderen,
            "konu": mail.konu,
            "kategori": kategori,
            "aksiyon": aksiyon,
            "neden": neden,
        }
        if ek:
            kayit.update(ek)
        with open(self.dosya, "a", encoding="utf-8") as f:
            f.write(json.dumps(kayit, ensure_ascii=False) + "\n")

