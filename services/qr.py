"""QR-коды для тестеров: PNG, ZIP-архив и печатный HTML-лист."""
import base64
import html
import io
import re
import secrets
import zipfile

import qrcode

# Алфавит без похожих символов (0/O, 1/I)
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def gen_tester_code(n: int = 6) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(n))


def deep_link(bot_username: str, code: str) -> str:
    return f"https://t.me/{bot_username}?start=c-{code}"


def qr_png_bytes(link: str, box_size: int = 10, border: int = 2) -> bytes:
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(link)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def store_zip(store: dict, testers: list[dict], bot_username: str) -> bytes:
    """ZIP: {код}.png для каждого тестера + labels.txt со ссылками."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        lines = ["код\tтестер\tместо\tссылка"]
        for t in testers:
            link = deep_link(bot_username, t["code"])
            zf.writestr(f"{t['code']}.png", qr_png_bytes(link))
            lines.append(f"{t['code']}\t{t['brand']} — {t['product']}\t{t['location']}\t{link}")
        zf.writestr("labels.txt", "\n".join(lines) + "\n")
    return buf.getvalue()


def _slug(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9а-яА-Я]+", "_", text).strip("_")
    return s or "store"


def printable_html(store: dict, testers: list[dict], bot_username: str) -> str:
    """Самодостаточный HTML для печати: карточки с QR и этикетками."""
    cards = []
    for t in testers:
        link = deep_link(bot_username, t["code"])
        png = base64.b64encode(qr_png_bytes(link, box_size=8)).decode()
        cards.append(f"""
      <div class="card">
        <div class="title">Не работает тестер?</div>
        <div class="subtitle">Отсканируйте код и сообщите нам</div>
        <img src="data:image/png;base64,{png}" alt="QR">
        <div class="brand">{html.escape(t['brand'])}</div>
        <div class="product">{html.escape(t['product'])}</div>
        <div class="location">{html.escape(t['location'])}</div>
        <div class="code">{t['code']}</div>
      </div>""")
    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>QR — {html.escape(store['name'])}</title>
<style>
  body {{ font-family: Arial, sans-serif; margin: 20px; color: #000; }}
  h1 {{ font-size: 18px; }}
  .grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; }}
  .card {{
    border: 2px dashed #888; border-radius: 10px; padding: 14px;
    text-align: center; page-break-inside: avoid;
  }}
  .title {{ font-size: 16px; font-weight: bold; }}
  .subtitle {{ font-size: 12px; color: #444; margin: 4px 0 8px; }}
  img {{ width: 170px; height: 170px; }}
  .brand {{ font-size: 15px; font-weight: bold; margin-top: 8px; }}
  .product {{ font-size: 12px; }}
  .location {{ font-size: 11px; color: #555; }}
  .code {{ font-size: 11px; color: #999; margin-top: 4px; }}
  .footer {{ font-size: 12px; color: #666; margin-top: 16px; }}
  @media print {{ body {{ margin: 0; }} }}
</style>
</head>
<body>
<h1>Магазин: {html.escape(store['name'])}</h1>
<p class="footer">Распечатайте лист, вырежьте карточки и разместите рядом с соответствующими тестерами
(бренд и место указаны на каждой карточке). Бот: @{html.escape(bot_username)}</p>
<div class="grid">{''.join(cards)}
</div>
</body>
</html>"""


def file_stem(store: dict) -> str:
    return f"qr_{_slug(store['name'])}_{store['id']}"
