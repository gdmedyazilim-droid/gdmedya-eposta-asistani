#!/usr/bin/env python3
"""E-Posta Asistanı (GD Medya) — ana koşucu.

    python asistan.py --calistir          Gerçek Gmail: gereksizi okundu yap, taslak yaz, Telegram özeti at
    python asistan.py --kuru              Gerçek Gmail'i okur + AI kararını gösterir, HİÇBİR ŞEYİ değiştirmez
    python asistan.py --demo              Gmail yerine ornek_kutu/ klasörü (gerçek OpenAI ile)
    python asistan.py --demo --sahte-ai   Tamamen çevrimdışı deneme (ağ ve anahtar gerekmez)

Ek bayraklar:
    --limit N        Bu koşuda en fazla N mail işle
    --telegram-yok   Telegram özetini gönderme

Bu program hiçbir koşulda mail GÖNDERMEZ. Yanıtlar yalnız taslak olarak kaydedilir.
Çıkış kodu: 0 temiz, 1 en az bir mailde hata, 2 kurulum/ön koşul hatası.
"""
import argparse
import datetime
import glob
import json
import os
import re
import sys

import ortam
from ai_analiz import analiz_et, sahte_analiz
from bildirim import gonder as telegram_gonder
from bildirim import ozet_metni
from defter import Defter
from gmail_istemci import Mail, yanit_konusu

KOK = ortam.KOK


# ─── Kaynaklar ──────────────────────────────────────────────────

class DemoKaynak:
    """ornek_kutu/*.json dosyalarını gelen kutusu gibi sunar. Gmail'e dokunmaz."""

    adres = "demo@ornek_kutu"

    def __init__(self, klasor):
        self.klasor = klasor

    def okunmamislar(self, sorgu, limit):
        mailler = []
        for yol in sorted(glob.glob(os.path.join(self.klasor, "*.json")))[:limit]:
            with open(yol, encoding="utf-8") as f:
                v = json.load(f)
            mailler.append(Mail(
                id=v["id"], thread_id=v.get("thread_id", v["id"]),
                gonderen=v["gonderen"], konu=v["konu"], tarih=v.get("tarih", ""),
                govde=v["govde"], etiketler=v.get("etiketler", []),
                yanit_adresi=v.get("yanit_adresi", v["gonderen"]),
                message_id=v.get("message_id", ""),
                liste_aboneligi=v.get("liste_aboneligi", False),
            ))
        return mailler

    def okundu_isaretle(self, mail):
        pass

    def taslak_olustur(self, mail, govde):
        return "demo-taslak-" + mail.id


# ─── Karar mantığı (saf fonksiyonlar, dogrula.py bunları sınar) ──

def _listede(adres, liste):
    adres = (adres or "").lower()
    return next((k for k in liste if k and k.lower() in adres), None)


def on_eleme(mail, ayarlar):
    """AI'ya sormadan okundu yapılacak mailler. Neden metni ya da None döner."""
    if _listede(mail.gonderen_adres, ayarlar.get("beyaz_liste_gonderenler", [])):
        return None
    kara = _listede(mail.gonderen_adres, ayarlar.get("kara_liste_gonderenler", []))
    if kara:
        return "kara liste ({})".format(kara)
    for etiket in ayarlar.get("on_eleme_gmail_kategorileri", []):
        if etiket in mail.etiketler:
            return "Gmail kategorisi ({})".format(etiket)
    return None


def karar_ver(analiz, ayarlar, mail=None):
    """AI analizini aksiyona çevirir: OKUNDU / TASLAK / DOKUNMA."""
    kategori = analiz["kategori"]
    guven = float(analiz.get("guven_skoru", 0))
    esik = float(ayarlar.get("okundu_guven_esigi", 0.75))

    if kategori in ("PROMOSYON", "GEREKSIZ"):
        if mail is not None and _listede(mail.gonderen_adres,
                                         ayarlar.get("beyaz_liste_gonderenler", [])):
            return "DOKUNMA", "{} ama gönderen beyaz listede".format(kategori)
        if not ayarlar.get("gereksizleri_okundu_yap", True):
            return "DOKUNMA", "{} (okundu yapma kapalı)".format(kategori)
        if guven >= esik:
            return "OKUNDU", "{} (güven {:.2f})".format(kategori, guven)
        return "DOKUNMA", "{} ama güven düşük ({:.2f}), okunmamış bırakıldı".format(kategori, guven)

    if kategori == "YANIT_GEREKLI":
        if (analiz.get("taslak_yanit") or "").strip():
            return "TASLAK", "yanıt gerekli (güven {:.2f})".format(guven)
        return "DOKUNMA", "yanıt gerekli ama taslak boş geldi"

    return "DOKUNMA", "önemli bilgi, okunmamış bırakıldı"


_KAPANIS = re.compile(
    r"^\s*(saygılarımızla|saygılarımla|saygılar|iyi çalışmalar( dileriz| dilerim)?|"
    r"teşekkürler|teşekkür ederiz|sevgiler|kind regards|best regards|regards|"
    r"best|sincerely|thanks|thank you)[\s,.!]*$",
    re.IGNORECASE)


def kapanis_temizle(govde):
    """Modelin talimata rağmen eklediği sondaki kapanış satırlarını siler.

    İmza her zaman ayarlar.json'dan eklenir; çift 'Saygılarımızla' olmasın.
    Yalnız SONDAKİ, tek başına duran kapanış satırları silinir; metin içi
    'teşekkür ederiz' cümlelerine dokunulmaz.
    """
    satirlar = govde.rstrip().splitlines()
    while satirlar and (not satirlar[-1].strip() or _KAPANIS.match(satirlar[-1])):
        satirlar.pop()
    return "\n".join(satirlar).rstrip()


def taslak_metni(analiz, ayarlar):
    govde = kapanis_temizle(analiz["taslak_yanit"])
    imza = (ayarlar.get("imza") or "").strip()
    return govde + ("\n\n" + imza if imza else "")


def _dosya_adi(metin):
    temiz = re.sub(r"[^\w\-]+", "_", metin, flags=re.UNICODE).strip("_")
    return temiz[:50] or "konusuz"


def lokal_taslak_yaz(klasor, mail, analiz, metin, gmail_taslak_id):
    os.makedirs(klasor, exist_ok=True)
    zaman = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    taban = os.path.join(klasor, "{}_{}".format(zaman, _dosya_adi(mail.konu)))
    alanlar = analiz.get("doldurulacak_alanlar") or []
    with open(taban + ".txt", "w", encoding="utf-8") as f:
        f.write("Kime        : {}\n".format(mail.yanit_adresi or mail.gonderen))
        f.write("Konu        : {}\n".format(yanit_konusu(mail.konu)))
        f.write("Özet        : {}\n".format(analiz.get("ozet", "")))
        f.write("Doldurulacak: {}\n".format(", ".join(alanlar) or "-"))
        f.write("Gmail taslak: {}\n".format(gmail_taslak_id or "(oluşturulmadı)"))
        f.write("\n======== TASLAK (GÖNDERİLMEDİ) ========\n\n")
        f.write(metin)
        f.write("\n\n======== ORİJİNAL MAİL ========\n")
        f.write("Gönderen: {}\nTarih: {}\n\n".format(mail.gonderen, mail.tarih))
        f.write((mail.govde or "")[:4000])
    kayit = {
        "mail_id": mail.id, "thread_id": mail.thread_id,
        "kime": mail.yanit_adresi or mail.gonderen,
        "konu": yanit_konusu(mail.konu), "taslak": metin,
        "ozet": analiz.get("ozet", ""), "neden": analiz.get("neden", ""),
        "doldurulacak_alanlar": alanlar, "gmail_taslak_id": gmail_taslak_id,
    }
    with open(taban + ".json", "w", encoding="utf-8") as f:
        json.dump(kayit, f, ensure_ascii=False, indent=2)
    return taban + ".txt"


# ─── Koşu ───────────────────────────────────────────────────────

def bayraklar(argv=None):
    p = argparse.ArgumentParser(description="GD Medya E-Posta Asistanı")
    mod = p.add_mutually_exclusive_group(required=True)
    mod.add_argument("--calistir", action="store_true", help="gerçek koşu")
    mod.add_argument("--kuru", action="store_true", help="hiçbir şeyi değiştirmeden kararları göster")
    mod.add_argument("--demo", action="store_true", help="ornek_kutu/ ile dene")
    p.add_argument("--sahte-ai", action="store_true", help="OpenAI yerine kural tabanlı taklit")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--telegram-yok", action="store_true")
    p.add_argument("--ayar", default=os.path.join(KOK, "ayarlar.json"))
    return p.parse_args(argv)


def kos(b):
    ortam.konsolu_hazirla()
    ortam.env_yukle()
    # utf-8-sig: Not Defteri'nin eklediği BOM işaretini tolere eder
    with open(b.ayar, encoding="utf-8-sig") as f:
        ayarlar = json.load(f)

    durum = os.path.join(KOK, "durum", "demo" if b.demo else "")
    log = ortam.Gunluk(os.path.join(durum, "kosu.log"))
    degistir = not b.kuru  # kuru koşuda Gmail'e, deftere ve taslak klasörüne hiçbir şey yazılmaz
    limit = b.limit or int(ayarlar.get("maksimum_mail_sayisi", 30))
    mod_adi = "DEMO" if b.demo else ("KURU (değişiklik yok)" if b.kuru else "ÇALIŞTIR")

    # AI seçimi
    if b.sahte_ai:
        analizci, api = sahte_analiz, None
    else:
        api = ortam.gercek_deger("OPENAI_API_KEY")
        if not api:
            log("❌ OPENAI_API_KEY master.env içinde yok. Çıkılıyor.")
            return 2
        analizci = analiz_et

    # Kaynak seçimi
    try:
        if b.demo:
            kaynak = DemoKaynak(os.path.join(KOK, "ornek_kutu"))
        else:
            from gmail_istemci import GmailKaynak
            kaynak = GmailKaynak(ayarlar["hesap"])
    except Exception as e:
        log("❌ Gmail bağlantısı kurulamadı: {}".format(e))
        log("   Çözüm: python yetkilendir.py  (KURULUM.md, Adım 2)")
        return 2

    defter = Defter(None if (b.demo or b.kuru) else os.path.join(durum, "defter.jsonl"))
    log("━" * 60)
    log("📧 E-Posta Asistanı | mod: {} | hesap: {} | model: {}".format(
        mod_adi, kaynak.adres, "sahte" if b.sahte_ai else ayarlar.get("openai_model")))

    try:
        mailler = kaynak.okunmamislar(ayarlar.get("gmail_sorgu", "is:unread in:inbox"), limit)
    except Exception as e:
        log("❌ Mailler okunamadı: {}".format(e))
        return 2

    rapor = {"sayac": dict.fromkeys(("taranan", "okundu", "taslak", "onemli", "hata", "atlandi"), 0),
             "taslaklar": [], "onemliler": [], "hatalar": []}
    toplam_token = 0
    log("📥 {} okunmamış mail bulundu".format(len(mailler)))

    for mail in mailler:
        if defter.var_mi(mail.id):
            rapor["sayac"]["atlandi"] += 1
            continue
        rapor["sayac"]["taranan"] += 1
        etiket = "{} | {}".format(mail.gonderen_adi[:28], mail.konu[:50])

        try:
            neden = on_eleme(mail, ayarlar)
            if neden:
                analiz = {"kategori": "PROMOSYON", "ozet": "", "doldurulacak_alanlar": []}
                aksiyon, neden = "OKUNDU", "ön eleme: " + neden
            else:
                analiz = analizci(mail, ayarlar, api)
                toplam_token += analiz.get("_kullanim", {}).get("total_tokens", 0)
                aksiyon, neden = karar_ver(analiz, ayarlar, mail)

            ek = {}
            if aksiyon == "OKUNDU":
                if degistir:
                    kaynak.okundu_isaretle(mail)
                rapor["sayac"]["okundu"] += 1
                log("  👁  OKUNDU  {}  — {}".format(etiket, neden))

            elif aksiyon == "TASLAK":
                metin = taslak_metni(analiz, ayarlar)
                gmail_id, lokal = None, None
                if degistir and ayarlar.get("gmail_taslak_olustur", True):
                    gmail_id = kaynak.taslak_olustur(mail, metin)
                if degistir and ayarlar.get("lokal_taslak_kaydet", True):
                    lokal = lokal_taslak_yaz(os.path.join(durum, "taslaklar"),
                                             mail, analiz, metin, gmail_id)
                rapor["sayac"]["taslak"] += 1
                rapor["taslaklar"].append({
                    "gonderen": mail.gonderen_adi, "konu": mail.konu,
                    "ozet": analiz.get("ozet", ""),
                    "doldurulacak": analiz.get("doldurulacak_alanlar") or []})
                ek = {"gmail_taslak_id": gmail_id, "lokal_taslak": lokal}
                log("  ✍️  TASLAK  {}  — {}".format(etiket, analiz.get("ozet", "")))
                if b.kuru or b.demo:
                    for satir in metin.splitlines():
                        log("        │ " + satir)

            else:
                rapor["sayac"]["onemli"] += 1
                rapor["onemliler"].append({"gonderen": mail.gonderen_adi, "konu": mail.konu})
                log("  📌 DOKUNMA {}  — {}".format(etiket, neden))

            if degistir:
                defter.yaz(mail, analiz["kategori"], aksiyon, neden, ek)

        except Exception as e:  # bir mailin hatası (AnalizHatasi dahil) koşuyu durdurmaz
            rapor["sayac"]["hata"] += 1
            rapor["hatalar"].append({"konu": mail.konu, "hata": str(e)})
            log("  ⚠️  HATA    {}  — {}".format(etiket, e))

    s = rapor["sayac"]
    log("─" * 60)
    log("Sonuç: {} tarandı | {} okundu | {} taslak | {} önemli | {} hata | {} daha önce işlenmiş".format(
        s["taranan"], s["okundu"], s["taslak"], s["onemli"], s["hata"], s["atlandi"]))
    if toplam_token:
        log("OpenAI token kullanımı: {}".format(toplam_token))
    if b.kuru:
        log("KURU KOŞU: Gmail'de hiçbir şey değiştirilmedi, taslak kaydedilmedi.")

    if b.calistir and ayarlar.get("telegram_bildirim", True) and not b.telegram_yok:
        tarih = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
        _, aciklama = telegram_gonder(ozet_metni(rapor, tarih, kaynak.adres))
        log("📲 " + aciklama)

    return 1 if s["hata"] else 0


def main(argv=None):
    return kos(bayraklar(argv))


if __name__ == "__main__":
    sys.exit(main())
