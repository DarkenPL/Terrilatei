#!/usr/bin/env python3
"""Testy synchronizacji raportów z Google Docs (uruchamia je też GitHub Actions).

python3 narzedzia/test_synchronizuj_docs.py
"""
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

TU = Path(__file__).resolve().parent
sys.path.insert(0, str(TU))
import synchronizuj_docs as sd  # noqa: E402
from konwersja import karta_md  # noqa: E402

DOK_ID = next(iter(sd.DOKUMENTY))
WZORCE = TU / "wzorce"


# ------------------------------------------------------------ sztuczny dokument

def run(tekst, **styl):
    return {"textRun": {"content": tekst, "textStyle": styl}}


def akapit(*runy, styl="NORMAL_TEXT", lista=None, poziom=0):
    p = {"elements": [run(r) if isinstance(r, str) else r for r in runy],
         "paragraphStyle": {"namedStyleType": styl}}
    if lista:
        p["bullet"] = {"listId": lista, **({"nestingLevel": poziom} if poziom else {})}
    return {"paragraph": p}


def tabela(*wiersze):
    return {"table": {"tableRows": [{"tableCells": [{"content": [akapit(k + "\n")]} for k in w]}
                                    for w in wiersze]}}


LISTY = {
    "punkty": {"listProperties": {"nestingLevels": [{"glyphSymbol": "•", "glyphFormat": "%0"},
                                                    {"glyphSymbol": "o", "glyphFormat": "%1"}]}},
    "zadania": {"listProperties": {"nestingLevels": [{"glyphType": "GLYPH_TYPE_UNSPECIFIED",
                                                      "glyphFormat": "%0"}]}},
    "numery": {"listProperties": {"nestingLevels": [{"glyphType": "DECIMAL", "glyphFormat": "%0."}]}},
}


def karta(tytul, tresc):
    return {"tabProperties": {"title": tytul, "tabId": tytul},
            "documentTab": {"body": {"content": [{"sectionBreak": {}}] + tresc}, "lists": LISTY}}


def raport(nr, *tresc):
    return [akapit(f"Spalony Gulasz w Szemrotach — raport z sesji {nr}\n", styl="HEADING_1"),
            *tresc]


def dokument(raporty, rewizja="r1"):
    """raporty: {nr: [elementy treści]} – karty „Raport sesja 2026MMDD”."""
    karty = [karta("Ogłoszenie", [akapit("Ogłoszenie\n", styl="HEADING_1")])]
    for nr, tresc in sorted(raporty.items()):
        karty.append(karta(f"Raport sesja 202609{nr:02d}", raport(nr, *tresc)))
    return {"content": {"documentId": DOK_ID, "title": "Spalony Gulasz w Szemrotach",
                        "revisionId": rewizja, "tabs": karty}}


def prosty(nr, tekst):
    return [akapit(f"{tekst}\n")]


class Repo:
    """Tymczasowe repo gita z folderem raporty/ i narzedzia/."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = Path(self.tmp.name)
        (self.p / "raporty").mkdir()
        (self.p / "narzedzia").mkdir()
        self.git("init", "-q")
        self.git("config", "user.email", "t@t")
        self.git("config", "user.name", "t")
        self.n = 0

    def git(self, *a):
        subprocess.run(["git", "-C", str(self.p), *a], check=True, capture_output=True)

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", "x")

    def json(self, dok):
        self.n += 1
        f = self.p / f"dok{self.n}.json"
        f.write_text(json.dumps(dok, ensure_ascii=False), encoding="utf-8")
        t = time.time() + self.n          # każdy kolejny JSON „pobrany” później
        os.utime(f, (t, t))
        return str(f)

    def sd(self, *argv):
        out = io.StringIO()
        kod = 0
        with contextlib.redirect_stdout(out):
            try:
                sd.main([*argv, "--repo", str(self.p)])
            except SystemExit as e:
                kod = e.code if isinstance(e.code, int) else 1
                if not isinstance(e.code, int) and e.code:
                    print(e.code)
        return kod, out.getvalue()

    def plik(self, nr):
        return self.p / "raporty" / f"sesja-{nr:02d}.md"


# ------------------------------------------------------------------- testy

class Wzorzec(unittest.TestCase):
    """Prawdziwy wycinek JSON-a z Google Docs → ręcznie sprawdzony Markdown."""

    def test_wynik_identyczny_z_oczekiwanym(self):
        dok = json.loads((WZORCE / "google-docs.json").read_text("utf-8"))["content"]
        wynik = sd.raporty_z_dokumentu(dok, "Raport sesja")
        oczekiwane = sorted(p.name for p in (WZORCE / "oczekiwane").glob("*.md"))
        self.assertEqual(sorted(n for n, *_ in wynik.values()), oczekiwane)
        for nazwa, md, info, _ in wynik.values():
            self.assertEqual(md, (WZORCE / "oczekiwane" / nazwa).read_text("utf-8"), nazwa)
            self.assertEqual(info["pominiete"], {}, nazwa)

    def test_struktura_odpowiedzi(self):
        dane = json.loads((WZORCE / "google-docs.json").read_text("utf-8"))
        dok = dane["content"]
        for klucz in ("documentId", "revisionId", "title", "tabs"):
            self.assertIn(klucz, dok)
        for k in dok["tabs"]:
            self.assertIn("title", k["tabProperties"])
            self.assertIn("content", k["documentTab"]["body"])
        self.assertIn(dok["documentId"], sd.DOKUMENTY)


class Konwersja(unittest.TestCase):
    def md(self, *tresc):
        return karta_md(karta("Raport sesja 20260901", list(tresc)))

    def test_naglowki_i_akapity(self):
        md, _ = self.md(akapit("Tytuł\n", styl="HEADING_1"), akapit("Część\n", styl="HEADING_2"),
                        akapit("Pod\n", styl="HEADING_3"), akapit("Tekst.\n"), akapit("\n"))
        self.assertEqual(md, "# Tytuł\n\n## Część\n\n### Pod\n\nTekst.\n")

    def test_listy(self):
        md, _ = self.md(akapit("a\n", lista="punkty"), akapit("b\n", lista="punkty", poziom=1),
                        akapit("Przerwa\n"),
                        akapit("x\n", lista="zadania"),
                        akapit(run("y\n", strikethrough=True), lista="zadania"),
                        akapit("jeden\n", lista="numery"), akapit("dwa\n", lista="numery"))
        self.assertEqual(md, "- a\n  - b\n\nPrzerwa\n\n- [ ] x\n- [x] y\n\n1. jeden\n2. dwa\n")

    def test_lista_bez_formatu_to_punktor(self):
        listy = {"dziwna": {"listProperties": {"nestingLevels": [{"glyphType": "GLYPH_TYPE_UNSPECIFIED"}]}}}
        k = karta("R", [akapit("a\n", lista="dziwna")])
        k["documentTab"]["lists"] = listy
        self.assertEqual(karta_md(k)[0], "- a\n")

    def test_wyroznienia_i_link(self):
        md, _ = self.md(akapit(run("Kamery.", bold=True), " Są ", run("cztery", italic=True), ", ",
                               run("tu", link={"url": "https://x.pl"}), ".\n"))
        self.assertEqual(md, "**Kamery.** Są *cztery*, [tu](https://x.pl).\n")

    def test_tabela_naglowek_bez_pogrubienia(self):
        t = tabela(["#", "Żeton"], ["1", "V|X"])
        for k in t["table"]["tableRows"][0]["tableCells"]:
            k["content"][0]["paragraph"]["elements"][0]["textRun"]["textStyle"]["bold"] = True
        md, _ = self.md(t)
        self.assertEqual(md, "| # | Żeton |\n| --- | --- |\n| 1 | V\\|X |\n")

    def test_notatki_claude_i_podswietlenie(self):
        zolty = {"color": {"rgbColor": {"red": 1, "green": 1}}}
        md, info = self.md(akapit("Ida ", run("żyje", backgroundColor=zolty),
                                  run(" [Claude: poprawione imię]", bold=True), ".\n"),
                           akapit(run("[Claude: sam komentarz]\n", bold=True)))
        self.assertEqual(md, "Ida żyje.\n")
        self.assertEqual(info["podswietlone"], ["żyje"])
        self.assertEqual(len(info["notatki"]), 2)

    def test_nieznany_element_zgloszony(self):
        md, info = self.md(akapit("a", {"inlineObjectElement": {}}, "\n"))
        self.assertEqual(info["pominiete"], {"inlineObjectElement": 1})

    def test_numer_z_tytulu_i_kolejnosc_kart(self):
        dok = dokument({1: prosty(1, "a"), 3: prosty(3, "c")})["content"]
        self.assertEqual(sorted(sd.raporty_z_dokumentu(dok, "Raport sesja")), [1, 3])


class Obieg(unittest.TestCase):
    def setUp(self):
        self.r = Repo()
        dok = dokument({1: prosty(1, "Pierwsza."), 2: prosty(2, "Druga.")})
        j = self.r.json(dok)
        self.assertEqual(self.r.sd("inicjuj", j)[0], 0)
        kod, out = self.r.sd("zapisz", j, "wszystko")
        self.assertEqual(kod, 0, out)
        self.r.commit()

    def tearDown(self):
        self.r.tmp.cleanup()

    def stan(self, j):
        """{numer sesji: status} z wyniku „raport” (bez raportów BEZ ZMIAN)."""
        wynik = {}
        for l in self.r.sd("raport", j)[1].splitlines():
            m = re.match(r"^(?:  |!!)\s*(\d+)  (.+?)\s{2,}sesja-", l)
            if m:
                wynik[int(m.group(1))] = m.group(2)
        return wynik

    def test_nowy_i_bez_zmian(self):
        self.assertIn("Pierwsza.", self.r.plik(1).read_text("utf-8"))
        j = self.r.json(dokument({1: prosty(1, "Pierwsza."), 2: prosty(2, "Druga.")}))
        kod, out = self.r.sd("raport", j)
        self.assertIn("bez zmian: 1–2", out)
        self.assertEqual(self.r.sd("sprawdz")[0], 0)

    def test_zmiany_w_docs_zapisane(self):
        j = self.r.json(dokument({1: prosty(1, "Pierwsza poprawiona."), 2: prosty(2, "Druga."),
                                  3: prosty(3, "Trzecia.")}))
        self.assertEqual(self.stan(j), {1: "ZMIANY W DOCS", 3: "NOWY"})
        kod, out = self.r.sd("pokaz", j, "1")
        self.assertIn("{+Pierwsza poprawiona.+}", out)
        self.assertEqual(self.r.sd("zapisz", j, "wszystko")[0], 0)
        self.assertIn("poprawiona", self.r.plik(1).read_text("utf-8"))
        self.assertTrue(self.r.plik(3).exists())
        self.assertEqual(self.r.sd("sprawdz")[0], 0)

    def test_zmiana_tylko_w_repo_blokuje(self):
        self.r.plik(1).write_text(self.r.plik(1).read_text("utf-8").replace("Pierwsza", "Ręczna"), "utf-8")
        self.assertEqual(self.r.sd("sprawdz")[0], 1)
        j = self.r.json(dokument({1: prosty(1, "Pierwsza."), 2: prosty(2, "Druga.")}))
        self.assertEqual(self.stan(j)[1], "TYLKO W REPO")
        kod, out = self.r.sd("zapisz", j, "1")
        self.assertEqual(kod, 1)
        self.assertIn("Ręczna", self.r.plik(1).read_text("utf-8"))
        kod, out = self.r.sd("pokaz", j, "1")
        self.assertIn("co zmieniono w REPO", out)

    def test_konflikt_i_wymuszenie(self):
        self.r.plik(1).write_text("# ręcznie\n", "utf-8")
        j = self.r.json(dokument({1: prosty(1, "Pierwsza z Docs."), 2: prosty(2, "Druga.")}))
        self.assertEqual(self.stan(j)[1], "KONFLIKT")
        self.assertEqual(self.r.sd("zapisz", j, "1")[0], 1)
        self.assertEqual(self.r.sd("zapisz", j, "1", "--nadpisz-repo", "1")[0], 0)
        self.assertIn("z Docs", self.r.plik(1).read_text("utf-8"))

    def test_zgodne(self):
        nowy = "Pierwsza w obu."
        j = self.r.json(dokument({1: prosty(1, nowy), 2: prosty(2, "Druga.")}))
        md = sd.raporty_z_dokumentu(json.loads(Path(j).read_text())["content"], "Raport sesja")[1][1]
        self.r.plik(1).write_text(md, "utf-8")
        self.assertEqual(self.stan(j)[1], "ZGODNE")
        self.assertEqual(self.r.sd("zapisz", j, "1")[0], 0)
        self.assertEqual(self.r.sd("sprawdz")[0], 0)

    def test_usuniety_w_repo_i_brak_w_docs(self):
        self.r.plik(2).unlink()
        j = self.r.json(dokument({1: prosty(1, "Pierwsza."), 2: prosty(2, "Druga.")}))
        self.assertEqual(self.stan(j)[2], "USUNIĘTY W REPO")
        self.assertEqual(self.r.sd("zapisz", j, "2")[0], 1)
        self.r.git("checkout", "--", "raporty/sesja-02.md")
        j = self.r.json(dokument({1: prosty(1, "Pierwsza.")}))
        self.assertEqual(self.stan(j)[2], "BRAK W DOCS")
        self.r.sd("zapisz", j, "wszystko")
        self.assertTrue(self.r.plik(2).exists())

    def test_stary_json_odrzucony(self):
        stary = self.r.json(dokument({1: prosty(1, "Stara."), 2: prosty(2, "Druga.")}))
        os.utime(stary, (1, 1))
        kod, out = self.r.sd("zapisz", stary, "1")
        self.assertEqual(kod, 1)
        self.assertIn("starsza wersja", out)

    def test_masowa_zmiana_zablokowana(self):
        j = self.r.json(dokument({n: prosty(n, f"R{n}.") for n in range(1, 6)}))
        self.r.sd("zapisz", j, "wszystko")
        j = self.r.json(dokument({n: prosty(n, f"Inny {n}.") for n in range(1, 6)}))
        kod, out = self.r.sd("zapisz", j, "wszystko")
        self.assertEqual(kod, 1)
        self.assertIn("podejrzanie dużo", out)
        self.assertEqual(self.r.sd("zapisz", j, "wszystko", "--masowo")[0], 0)

    def test_zla_struktura_odrzucona(self):
        dok = dokument({1: prosty(1, "a")})
        del dok["content"]["tabs"][1]["documentTab"]["body"]
        kod, out = self.r.sd("zapisz", self.r.json(dok), "1")
        self.assertEqual(kod, 1)
        self.assertIn("oczekiwanej struktury", out)

    def test_sprawdz_wykrywa_notatke_i_nowy_plik(self):
        st = json.loads((self.r.p / sd.PLIK_STANU).read_text())
        tekst = self.r.plik(1).read_text("utf-8") + "x [Claude: ups]\n"
        self.r.plik(1).write_text(tekst, "utf-8")
        st["raporty"]["pliki"]["sesja-01.md"] = sd.sha(tekst)
        (self.r.p / sd.PLIK_STANU).write_text(json.dumps(st))
        (self.r.p / "raporty" / "sesja-09.md").write_text("# ręczny\n")
        kod, out = self.r.sd("sprawdz")
        self.assertEqual(kod, 1)
        self.assertIn("notatkę [Claude", out)
        self.assertIn("sesja-09.md: dodany", out)

    def test_inicjuj_z_commitu(self):
        r = Repo()
        r.plik(1).write_text("# z eksportu\n", "utf-8")
        r.commit()
        r.git("tag", "baza")
        r.plik(1).write_text("# poprawione w repo\n", "utf-8")
        r.commit()
        j = r.json(dokument({1: [akapit("z eksportu\n", styl="HEADING_1")]}))
        # karta ma też nagłówek „raport z sesji 1”, więc Docs ≠ baza → KONFLIKT, nie nadpisanie
        self.assertEqual(r.sd("inicjuj", j, "--baza", "baza")[0], 0)
        self.assertEqual(r.sd("sprawdz")[0], 1)
        kod, out = r.sd("zapisz", j, "1")
        self.assertEqual(kod, 1)
        self.assertIn("poprawione", r.plik(1).read_text("utf-8"))
        r.tmp.cleanup()


if __name__ == "__main__":
    unittest.main(verbosity=1)
