"""
🔐 Antigravity — Merkezi Google OAuth Yardımcısı
===================================================
Bu modül, tüm projelerde Google API erişimi sağlar.
Token'lar merkezi depoda saklanır ve otomatik yenilenir.

Desteklenen ortamlar:
  - Lokal (Mac): _knowledge/credentials/oauth/ dizinindeki token dosyaları
  - Railway/Cloud: GOOGLE_<HESAP>_TOKEN_JSON environment variable'ından
    JSON string olarak okunur

Kullanım:
    from google_auth import get_gmail_service, get_sheets_service, get_drive_service

    # Outreach hesabı (<KULLANICI_ADI>@gmail.com)
    gmail = get_gmail_service("outreach")
    sheets = get_sheets_service("outreach")
    drive = get_drive_service("outreach")

Token dosyaları:
    _knowledge/credentials/oauth/gmail-outreach-token.json
"""

import os
import json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Merkezi token deposu dizini
OAUTH_DIR = os.path.dirname(os.path.abspath(__file__))

# Hesap → token dosyası eşlemesi
TOKEN_FILES = {
    "gdmedya": "gmail-gdmedya-token.json",  # GD Medya iş hesabı (E-Posta Asistanı)
    "outreach": "gmail-outreach-token.json",
    "ornek-site.com": "gmail-ornek-site.com-token.json",
    "personel": "gmail-personel-token.json",
    "takvim": "ornek-site.com-takvim-token.json",
}

# Hesap → Railway environment variable eşlemesi
TOKEN_ENV_VARS = {
    "gdmedya": "GOOGLE_GDMEDYA_TOKEN_JSON",
    "outreach": "GOOGLE_OUTREACH_TOKEN_JSON",
    "ornek-site.com": "GOOGLE_TOKEN_JSON",
    "personel": "GOOGLE_personel_TOKEN_JSON",
    "takvim": "GOOGLE_TAKVIM_TOKEN_JSON",
}

ALL_SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/spreadsheets',
]


def _get_credentials(account: str = "outreach") -> Credentials:
    """
    Merkezi token deposundan credentials al ve gerekirse yenile.
    
    Öncelik sırası:
      1. Lokal dosya: _knowledge/credentials/oauth/gmail-{account}-token.json
      2. Environment variable: GOOGLE_{ACCOUNT}_TOKEN_JSON (Railway/Cloud)

    Args:
        account: "outreach" (ornek5e41@gmail.com), "ornek-site.com", "personel"

    Returns:
        Geçerli Google OAuth Credentials objesi

    Raises:
        FileNotFoundError: Token ne dosyada ne env'de bulunamazsa
        ValueError: Bilinmeyen hesap adı
    """
    if account not in TOKEN_FILES:
        raise ValueError(
            f"Bilinmeyen hesap: '{account}'. "
            f"Geçerli hesaplar: {', '.join(TOKEN_FILES.keys())}"
        )

    token_path = os.path.join(OAUTH_DIR, TOKEN_FILES[account])
    env_var = TOKEN_ENV_VARS[account]
    loaded_from = None

    # 1) Lokal dosyadan oku
    if os.path.exists(token_path):
        with open(token_path, encoding="utf-8") as f:
            token_json = json.load(f)
        creds = Credentials.from_authorized_user_info(token_json, _token_scopes(token_json))
        loaded_from = "file"
    # 2) Environment variable'dan oku (Railway/Cloud)
    elif os.environ.get(env_var):
        token_json = json.loads(os.environ[env_var])
        creds = Credentials.from_authorized_user_info(token_json, _token_scopes(token_json))
        loaded_from = "env"
    else:
        raise FileNotFoundError(
            f"Token bulunamadı: Ne dosya ({token_path}) ne de env ({env_var}) mevcut.\n"
            f"Lokal çözüm: cd {OAUTH_DIR} && python3 auth_helper.py {account}\n"
            f"Railway çözüm: {env_var} env variable'ını token JSON'ı ile set et."
        )

    # Token süresi dolmuşsa otomatik yenile
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Yenilenen token'ı kaydet (sadece dosya varsa)
            if loaded_from == "file":
                _save_token(creds, token_path)
        else:
            raise RuntimeError(
                f"Token geçersiz ve yenilenemiyor. "
                f"Çözüm: cd {OAUTH_DIR} && python3 auth_helper.py {account}"
            )

    return creds


def _token_scopes(token_json: dict) -> list:
    """Token'ın KENDİ izinlerini kullan, ALL_SCOPES'u dayatma.

    Her hesap aynı izinlerle açılmadı (örn. personel yalnız Gmail izinleriyle açıldı).
    ALL_SCOPES dayatılınca yenileme 'invalid_scope' ile patlıyordu ve o hesabın
    otomasyonu token'ın ömrü dolduğu gün sessizce duruyordu. 2026-08-09'da yaşandı.
    """
    return token_json.get("scopes") or ALL_SCOPES


def _save_token(creds: Credentials, token_path: str):
    """Yenilenen token'ı dosyaya kaydet."""
    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else ALL_SCOPES,
        "universe_domain": "googleapis.com",
        "account": "",
        "expiry": creds.expiry.isoformat() + "Z" if creds.expiry else None,
    }
    # Sadece sahibi okuyabilsin (0600) — dosyada hesaba erişim anahtarı var.
    fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(token_data, f, indent=2)


def get_gmail_service(account: str = "outreach"):
    """Gmail API service objesi döndür."""
    return build('gmail', 'v1', credentials=_get_credentials(account))


def get_sheets_service(account: str = "outreach"):
    """Google Sheets API service objesi döndür."""
    return build('sheets', 'v4', credentials=_get_credentials(account))


def get_calendar_service(account: str = "takvim"):
    """Google Calendar API service objesi dondur.

    Varsayilan hesap `takvim` = ornekf84c@ornek-site.com kullanici izni.
    Servis hesabi DEGIL: kullanicinin KENDI birincil takvimine yazar.
    Kurum politikasi disaridan paylasimi free/busy ile sinirladigi icin
    servis hesabi o takvime yazamaz; kullanici izni bu duvari hic gormez.
    """
    return build('calendar', 'v3', credentials=_get_credentials(account))


def get_drive_service(account: str = "outreach"):
    """Google Drive API service objesi döndür."""
    return build('drive', 'v3', credentials=_get_credentials(account))


# ─── Kısa yol fonksiyonlar ───────────────────────────────────

def gmail_outreach():
    """ornek5e41@gmail.com Gmail service — kısa yol."""
    return get_gmail_service("outreach")


def sheets_outreach():
    """ornek5e41@gmail.com Sheets service — kısa yol."""
    return get_sheets_service("outreach")


def gmail_dolunay_ai():
    """ornekf84c@ornek-site.com Gmail service — kısa yol."""
    return get_gmail_service("ornek-site.com")


def sheets_dolunay_ai():
    """ornekf84c@ornek-site.com Sheets service — kısa yol."""
    return get_sheets_service("ornek-site.com")


def drive_dolunay_ai():
    """ornekf84c@ornek-site.com Drive service — kısa yol."""
    return get_drive_service("ornek-site.com")


def takvim_dolunay_ai():
    """ornekf84c@ornek-site.com birincil takvimi — kisa yol."""
    return get_calendar_service("takvim")


def gmail_personel():
    """ornekd774@ornek-site.com Gmail service — kısa yol."""
    return get_gmail_service("personel")



if __name__ == "__main__":
    # Quick test
    print("🔍 Google Auth merkezi modül testi...\n")
    for acc in TOKEN_FILES:
        try:
            creds = _get_credentials(acc)
            print(f"  ✅ {acc}: Token geçerli")
            print(f"     Scopes: {len(creds.scopes)} izin")
            print(f"     Expiry: {creds.expiry}")
        except Exception as e:
            print(f"  ❌ {acc}: {e}")
        print()
