"""bildirim.py — Koşu özetini Telegram'a gönderir.

TELEGRAM_BOT_TOKEN ve ADMIN_CHAT_ID master.env'de tanımlı değilse sessizce atlar
(koşu yine başarılı sayılır; özet günlük dosyasında durur).
"""
import ortam

TELEGRAM_SINIRI = 4000  # Telegram mesaj sınırı 4096; pay bırakıldı


def ozet_metni(rapor, tarih_metni, hesap_adresi):
    s = rapor["sayac"]
    satirlar = [
        "📧 E-Posta Asistanı — {}".format(tarih_metni),
        "Hesap: {}".format(hesap_adresi),
        "",
        "Taranan: {} | 👁 Okundu: {} | ✍️ Taslak: {} | 📌 Önemli: {} | ⚠️ Hata: {}".format(
            s["taranan"], s["okundu"], s["taslak"], s["onemli"], s["hata"]),
    ]
    if rapor["taslaklar"]:
        satirlar += ["", "✍️ Hazırlanan taslaklar (Gmail > Taslaklar):"]
        for i, t in enumerate(rapor["taslaklar"], 1):
            satirlar.append("{}. {} — {}".format(i, t["gonderen"], t["konu"]))
            satirlar.append("   {}".format(t["ozet"]))
            if t["doldurulacak"]:
                satirlar.append("   ✏️ Doldurulacak: {}".format(", ".join(t["doldurulacak"])))
    if rapor["onemliler"]:
        satirlar += ["", "📌 Önemli (okunmamış bırakıldı):"]
        for t in rapor["onemliler"]:
            satirlar.append("• {} — {}".format(t["gonderen"], t["konu"]))
    if rapor["hatalar"]:
        satirlar += ["", "⚠️ Hatalar (yarın tekrar denenecek):"]
        for t in rapor["hatalar"]:
            satirlar.append("• {} — {}".format(t["konu"], t["hata"][:120]))
    if not any((rapor["taslaklar"], rapor["onemliler"], rapor["hatalar"])):
        satirlar += ["", "Cevap bekleyen mail yok. ☕"]
    metin = "\n".join(satirlar)
    if len(metin) > TELEGRAM_SINIRI:
        metin = metin[:TELEGRAM_SINIRI] + "\n…(kısaltıldı, ayrıntı kosu.log'da)"
    return metin


def gonder(metin):
    """(gonderildi_mi, aciklama) döndürür."""
    token = ortam.gercek_deger("TELEGRAM_BOT_TOKEN")
    sohbet = ortam.gercek_deger("ADMIN_CHAT_ID")
    if not token or not sohbet:
        return False, "Telegram tanımlı değil (master.env: TELEGRAM_BOT_TOKEN / ADMIN_CHAT_ID), atlandı"
    import requests
    try:
        r = requests.post(
            "https://api.telegram.org/bot{}/sendMessage".format(token),
            json={"chat_id": sohbet, "text": metin, "disable_web_page_preview": True},
            timeout=20,
        )
    except requests.RequestException as e:
        return False, "Telegram ağ hatası: {}".format(e)
    if r.status_code != 200:
        return False, "Telegram {}: {}".format(r.status_code, r.text[:200])
    return True, "Telegram özeti gönderildi"

