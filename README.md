# 📧 E-Posta Asistanı (GD Medya)

GD Medya Gmail kutusunu her sabah 09:00'da tarar. Gereksiz mailleri **okundu** yapar, cevap bekleyen maillere **GD Medya adına yanıt taslağı** hazırlar.

> **Asla mail göndermez.** Taslaklar Gmail'de *Taslaklar* klasöründe, ilgili konuşmanın altında bekler. Beğenirseniz **Gönder**'e basarsınız, beğenmezseniz düzenleyip öyle gönderirsiniz.

Kurulum: [KURULUM.md](KURULUM.md) · Workflow: `_agents/workflows/eposta-asistani.md`

## Akış

```
09:00 (Görev Zamanlayıcı)
  │
  ▼
Gmail: is:unread in:inbox -from:me  (en fazla 30)
  │
  ├─ Ön eleme (AI'ya sormadan)  → Promosyon/Sosyal sekmesi, kara liste  → 👁 OKUNDU
  │
  └─ OpenAI gpt-4.1-mini (sabit JSON şeması)
        ├─ PROMOSYON / GEREKSIZ  (güven ≥ 0.75)  → 👁 OKUNDU
        ├─ PROMOSYON / GEREKSIZ  (güven düşük)   → 📌 dokunma
        ├─ ONEMLI_BILGI (fatura, banka, güvenlik) → 📌 dokunma (okunmamış kalır)
        └─ YANIT_GEREKLI                          → ✍️ Gmail taslağı + durum/taslaklar/*.txt
  │
  ▼
Telegram özeti  +  durum/kosu.log  +  durum/defter.jsonl
```

## Güvenlik kuralları

| Kural | Nasıl sağlanıyor |
|---|---|
| Mail gönderilmez | Kodda `send` çağrısı yok; `dogrula.py` kaynak kodu tarayıp kontrol eder |
| Fiyat/tarih uydurulmaz | AI `[FİYAT]`, `[TARİH]` gibi yer tutucu bırakır; Telegram'da "✏️ Doldurulacak" diye listelenir |
| Gerçek insan maili kaybolmaz | Emin olmadığında AI "önemli" seçer; düşük güvenli "gereksiz" kararları okundu yapılmaz |
| Önemli gönderen korunur | `beyaz_liste_gonderenler` içindekiler hiçbir zaman otomatik okundu yapılmaz |
| Aynı maile iki taslak yazılmaz | `durum/defter.jsonl` işlenen mailleri hatırlar |
| Kimlik | Taslaklar yalnız "GD Medya" kurumsal diliyle ("biz"), kişi adı olmadan yazılır |

## Komutlar

```powershell
python dogrula.py                       # 12 sınav, çevrimdışı
python asistan.py --demo --sahte-ai     # örnek kutu, ağ yok
python asistan.py --demo                # örnek kutu + gerçek OpenAI
python asistan.py --kuru --limit 10     # gerçek Gmail, hiçbir şey değişmez
python asistan.py --calistir            # canlı koşu
```

## Dosyalar

| Dosya | Görevi |
|---|---|
| `asistan.py` | Ana koşucu, karar mantığı |
| `ai_analiz.py` | OpenAI sınıflandırma + taslak (Structured Outputs) |
| `gmail_istemci.py` | Gmail okuma / okundu / taslak (gönderme yok) |
| `bildirim.py` | Telegram özeti |
| `defter.py` | İşlenen mail kaydı |
| `ortam.py` | Yollar, `master.env` okuma, günlük |
| `yetkilendir.py` | İlk seferlik Gmail girişi |
| `ayarlar.json` | Model, eşik, listeler, kurum profili, imza |
| `zamanlayici_kur.ps1` | Her gün 09:00 Windows görevi |
| `dogrula.py` | Kendi kendini sınama |
| `ornek_kutu/` | 5 örnek mail (demo) |
| `durum/` | Çıktılar: taslaklar, defter, günlük (git'e gitmez) |

## Ayarlar (`ayarlar.json`)

| Anahtar | Varsayılan | Anlamı |
|---|---|---|
| `openai_model` | `gpt-4.1-mini` | Ücretsiz token programındaki mini model; `gpt-4o-mini` daha ucuz ama vaat uydurmaya daha yatkın |
| `okundu_guven_esigi` | `0.75` | Bunun altındaki "gereksiz" kararları okundu yapılmaz |
| `maksimum_mail_sayisi` | `30` | Bir koşuda işlenecek en fazla mail |
| `gmail_taslak_olustur` | `true` | `false` yapılırsa taslak yalnız `durum/taslaklar/`'a yazılır |
| `kara_liste_gonderenler` | bülten/pazarlama adresleri | AI'ya sormadan okundu |
| `beyaz_liste_gonderenler` | `[]` | Asla otomatik okundu yapılmaz |
| `imza` | GD Medya Ekibi | Her taslağın altına eklenir |

