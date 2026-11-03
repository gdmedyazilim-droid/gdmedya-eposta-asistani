"""gmail_istemci.py — Gmail okuma, okundu işaretleme ve TASLAK oluşturma.

GÜVENLİK İLKESİ: Bu modülde mail GÖNDEREN hiçbir fonksiyon yoktur.
Yalnızca `drafts().create` kullanılır; `messages().send` veya `drafts().send`
çağrısı bilerek yazılmamıştır. `dogrula.py` bunu kaynak kodu tarayarak sınar.
"""
import base64
import html
import os
import re
import sys
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import parseaddr
from html.parser import HTMLParser

import ortam


@dataclass
class Mail:
    id: str
    thread_id: str
    gonderen: str            # "Ahmet Yılmaz <ahmet@otel.com>"
    konu: str
    tarih: str
    govde: str
    etiketler: list = field(default_factory=list)
    yanit_adresi: str = ""   # Reply-To varsa o, yoksa From
    message_id: str = ""     # RFC Message-ID başlığı (yanıt zinciri için)
    references: str = ""
    liste_aboneligi: bool = False  # List-Unsubscribe başlığı var mı (toplu mail işareti)

    @property
    def gonderen_adres(self):
        return parseaddr(self.gonderen)[1].lower()

    @property
    def gonderen_adi(self):
        return parseaddr(self.gonderen)[0] or self.gonderen_adres


# ─── Gövde çıkarma ──────────────────────────────────────────────

class _HtmlTemizleyici(HTMLParser):
    """HTML'i düz metne çevirir; script/style içeriğini atar."""

    _BLOK = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "table"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parcalar = []
        self._atla = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self._atla += 1
        elif tag in self._BLOK:
            self.parcalar.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head") and self._atla:
            self._atla -= 1
        elif tag in self._BLOK:
            self.parcalar.append("\n")

    def handle_data(self, data):
        if not self._atla:
            self.parcalar.append(data)


def html_temizle(metin):
    t = _HtmlTemizleyici()
    t.feed(metin)
    duz = html.unescape("".join(t.parcalar))
    duz = re.sub(r"[ \t\r\f\v]+", " ", duz)
    duz = re.sub(r"\n\s*\n+", "\n\n", duz)
    return duz.strip()


def _b64_coz(veri):
    if not veri:
        return ""
    ham = base64.urlsafe_b64decode(veri + "=" * (-len(veri) % 4))
    return ham.decode("utf-8", errors="replace")


def govde_cikar(payload):
    """Gmail payload ağacından okunabilir metni çıkarır (text/plain öncelikli)."""
    duz, htm = [], []

    def gez(parca):
        tip = parca.get("mimeType", "")
        veri = parca.get("body", {}).get("data")
        if parca.get("filename"):
            return  # ekleri atla
        if tip == "text/plain" and veri:
            duz.append(_b64_coz(veri))
        elif tip == "text/html" and veri:
            htm.append(_b64_coz(veri))
        for alt in parca.get("parts", []) or []:
            gez(alt)

    gez(payload)
    if duz:
        return "\n".join(duz).strip()
    if htm:
        return html_temizle("\n".join(htm))
    return ""


def yanit_konusu(konu):
    konu = (konu or "").strip()
    if re.match(r"^\s*(re|ynt|yanıt)\s*:", konu, flags=re.IGNORECASE):
        return konu
    return "Re: " + (konu or "(konusuz)")


def taslak_mime(mail, govde):
    """Orijinal mailin yanıt zincirine oturan bir MIME mesajı kurar (göndermez)."""
    msg = EmailMessage()
    msg["To"] = mail.yanit_adresi or mail.gonderen
    msg["Subject"] = yanit_konusu(mail.konu)
    if mail.message_id:
        msg["In-Reply-To"] = mail.message_id
        msg["References"] = (mail.references + " " + mail.message_id).strip()
    msg.set_content(govde, charset="utf-8")
    return msg


# ─── Gmail API sarmalayıcı ──────────────────────────────────────

class GmailKaynak:
    """Gerçek Gmail hesabı. Hesap adı google_auth.TOKEN_FILES içindeki anahtardır."""

    def __init__(self, hesap):
        if os.path.exists(ortam.OAUTH_DIR) and ortam.OAUTH_DIR not in sys.path:
            sys.path.insert(0, ortam.OAUTH_DIR)
        if ortam.KOK not in sys.path:
            sys.path.insert(0, ortam.KOK)
        import google_auth  # noqa: E402
        self.svc = google_auth.get_gmail_service(hesap)
        self.adres = self.svc.users().getProfile(userId="me").execute()["emailAddress"]

    def okunmamislar(self, sorgu, limit):
        r = self.svc.users().messages().list(
            userId="me", q=sorgu, maxResults=limit).execute()
        kimlikler = [m["id"] for m in r.get("messages", [])]
        # Gmail en yeniyi başa koyar; eskiden yeniye işlemek daha doğal.
        return [self.mail_getir(k) for k in reversed(kimlikler)]

    def mail_getir(self, kimlik):
        m = self.svc.users().messages().get(userId="me", id=kimlik, format="full").execute()
        b = {h["name"].lower(): h["value"] for h in m["payload"].get("headers", [])}
        return Mail(
            id=m["id"],
            thread_id=m["threadId"],
            gonderen=b.get("from", ""),
            konu=b.get("subject", "(konusuz)"),
            tarih=b.get("date", ""),
            govde=govde_cikar(m["payload"]) or m.get("snippet", ""),
            etiketler=m.get("labelIds", []),
            yanit_adresi=b.get("reply-to", "") or b.get("from", ""),
            message_id=b.get("message-id", ""),
            references=b.get("references", ""),
            liste_aboneligi="list-unsubscribe" in b,
        )

    def okundu_isaretle(self, mail):
        self.svc.users().messages().modify(
            userId="me", id=mail.id, body={"removeLabelIds": ["UNREAD"]}).execute()

    def taslak_olustur(self, mail, govde):
        """Gmail > Taslaklar'a, orijinal konuşmanın altına taslak bırakır. GÖNDERMEZ."""
        ham = base64.urlsafe_b64encode(taslak_mime(mail, govde).as_bytes()).decode()
        taslak = self.svc.users().drafts().create(
            userId="me",
            body={"message": {"raw": ham, "threadId": mail.thread_id}},
        ).execute()
        return taslak["id"]
