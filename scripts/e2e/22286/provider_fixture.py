"""Isolated HTTP fixture for documented FNS contracts; never a live provider."""
import base64
import io
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from reportlab.pdfgen import canvas


def pdf():
    output = io.BytesIO()
    page = canvas.Canvas(output)
    page.drawString(50, 750, "Synthetic EGRUL acceptance fixture #22286")
    page.save()
    return output.getvalue()


class Handler(BaseHTTPRequestHandler):
    def respond(self, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/dadata/findById/party" or self.headers.get("Authorization") != "Token fixture-only":
            self.send_error(403)
            return
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        mode_path = Path("/runtime/management-source-mode.json")
        mode = json.loads(mode_path.read_text()) if mode_path.exists() else "off"
        suggestions = []
        if mode in ("first", "second"):
            suggestions = [{"data": {
                "inn": body.get("query"),
                "managers": [{"type": "LEGAL", "name": "УК Источник 1" if mode == "first" else "УК Источник 2",
                    "inn": "7701234567", "ogrn": "1027700000000"}],
            }}]
        self.respond({"suggestions": suggestions})

    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        if query.get("key") != ["fixture-only"]:
            self.send_error(403)
            return
        mode_path = Path("/runtime/provider-mode.json")
        mode = json.loads(mode_path.read_text()) if mode_path.exists() else "success"
        if mode == "unavailable":
            self.send_error(503)
            return
        inn = query.get("inn", [None])[0]
        ogrn = query.get("ogrn", [None])[0]
        # Only synthetic identity/flags are recorded; never provider credentials.
        with Path("/runtime/provider-requests.jsonl").open("a") as log:
            log.write(json.dumps({"path": url.path, "inn": inn, "ogrn": ogrn,
                "includeAttributes": query.get("includeAttributes"), "skipPdf": query.get("skipPdf")}) + "\n")
        if "pdf_download" in url.path and query.get("includeAttributes") == ["1"]:
            if query.get("skipPdf") != ["1"]:
                self.send_error(400)
                return
            if mode == "foreign_unavailable":
                self.send_error(503)
                return
            if mode == "foreign_invalid_json":
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"{")
                return
            full = {"num": 4, "section": "Наименование", "subsection": None, "item": None,
                "name": "Полное наименование на английском языке",
                "value": "  Fixture International Two LLC  " if mode == "foreign_updated" else "  Fixture International One LLC  "}
            attributes = [
                {"num": 1, "section": "Наименование", "name": "Полное наименование на русском языке", "value": "ООО Тест"},
                {"num": 2, "section": "Другой раздел", "name": full["name"], "value": "Wrong Section LLC"},
                {"num": 3, "section": "Наименование", "name": "Сокращенное наименование на английском языке", "value": "Short LLC"},
                full,
            ]
            if mode == "foreign_empty":
                attributes = [{**full, "value": "  "}, {**full, "value": None}]
            elif mode == "foreign_wrong_section":
                attributes = attributes[:3]
            elif mode == "foreign_conflict":
                attributes.append({**full, "value": "Conflicting Company LLC"})
            elif mode == "foreign_duplicate":
                attributes.append({**full, "value": full["value"].strip()})
            elif mode == "foreign_invalid_shape":
                attributes = {"value": full["value"]}
            elif mode == "foreign_not_found":
                attributes = None
            data = {"success": 0 if mode == "foreign_failure" else 1,
                "file_name": None if attributes is None else "egrul-fixture.pdf",
                "extract_number": None if attributes is None else "synthetic-extract",
                "extract_date": None if attributes is None else "2026-10-01",
                "attributes": attributes}
        elif "pdf_download" in url.path:
            content = "invalid-base64" if mode == "invalid_pdf" else base64.b64encode(pdf()).decode()
            data = {"success": 1, "file_name": "egrul-fixture.pdf", "pdf_content": None if mode == "not_found" else content}
        elif "search_org" in url.path:
            data = {"success": 1, "org": [] if mode == "not_found" else [{
                "inn": "0000999999" if mode == "foreign_mismatch" else inn, "ogrn": ogrn,
                "name": "ООО Автоматическое ФНС", "name_short": "ООО ФНС",
                "registration_date": "2020-02-03", "reg_authority": {"name": "Тестовый регистрирующий орган"},
                "avg_headcount": [{"year": 2022, "count": 7}, {"year": 2025, "count": 42}, {"year": 2023, "count": 10}],
                "okved": "49.41", "okved_name": "Перевозки", "tax_modes": [],
                **({"address": "Москва, Адрес ФНС, 2" if mode == "address_updated" else "Москва, Адрес ФНС, 1"} if inn == "0000992287" else {}),
                **({"owner": [
                    {"inn": "000000009901", "name": "Автоматическое имя", "share": 45},
                    {"inn": "000000009902", "name": "Удалённый учредитель", "share": 55},
                ]} if inn == "0000992286" else {}),
            }]}
        else:
            data = {"success": 1, "ip": [] if mode == "not_found" else [{"inn": inn, "ogrn": ogrn, "name": "ИП Тестовый"}]}
        self.respond(data)

    def log_message(self, *_):
        pass


HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
