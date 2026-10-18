"""Zamiana karty raportu z Google Docs (JSON z read_doc) na Markdown.

Zasady (takie jak eksport Google Docs do Markdown, którym powstały pierwsze raporty):
  nagłówek 1/2/3… = #, ##, ###…; styl Title = #
  punktory = „- ” (zagnieżdżenie: 2 spacje na poziom), numerowane = „1. ”
  tabela = tabela Markdown (pierwszy wiersz to nagłówek)
  pogrubienie = **…**, kursywa = *…*, link = [tekst](url)
  między blokami pusta linia, między punktami tej samej listy nie
Pomijane: podświetlenie (znacznik zmian do przeczytania), wyjaśnienia [Claude: …],
podział strony, kolory i czcionki.
"""
import re

# Wyjaśnienia zmian od Claude'a w Docs – zostają tylko w Docs.
NOTATKA = re.compile(r"\s*\[Claude:[^\]]*\]")
ZNANE_ELEMENTY = {"startIndex", "endIndex", "textRun", "pageBreak"}
ZNANE_BLOKI = {"startIndex", "endIndex", "paragraph", "sectionBreak", "table", "tableOfContents"}


def podswietlony(styl):
    bg = styl.get("backgroundColor", {}).get("color", {}).get("rgbColor")
    return bool(bg) and bg != {"red": 1, "green": 1, "blue": 1}


def _owin(tekst, znak):
    m = re.fullmatch(r"(\s*)(.*?)(\s*)", tekst, re.S)
    return f"{m[1]}{znak}{m[2]}{znak}{m[3]}" if m[2] else tekst


def tekst_md(akapit, info=None):
    """Tekst akapitu jako Markdown (bez końcowego entera)."""
    kawalki = []                 # [(bold, italic, url), tekst] – sąsiednie o tym samym stylu scalone
    for el in akapit.get("elements", []):
        tr = el.get("textRun")
        if not tr:
            continue
        st = tr.get("textStyle", {})
        if info is not None and podswietlony(st) and tr["content"].strip():
            info["podswietlone"].append(tr["content"].strip())
        klucz = (bool(st.get("bold")), bool(st.get("italic")), st.get("link", {}).get("url"))
        if kawalki and kawalki[-1][0] == klucz:
            kawalki[-1][1] += tr["content"]
        else:
            kawalki.append([klucz, tr["content"]])
    out = []
    for (b, i, url), t in kawalki:
        t = t.replace("\n", "").replace("\u000b", "\n")
        if info is not None:
            info["notatki"] += [x.strip() for x in NOTATKA.findall(t)]
        t = NOTATKA.sub("", t)                    # notatka w osobnym, np. pogrubionym, kawałku
        if i:
            t = _owin(t, "*")
        if b:
            t = _owin(t, "**")
        if url:
            m = re.fullmatch(r"(\s*)(.*?)(\s*)", t, re.S)
            t = f"{m[1]}[{m[2]}]({url}){m[3]}" if m[2] else t
        out.append(t)
    tekst = "".join(out)
    if info is not None:
        info["notatki"] += [x.strip() for x in NOTATKA.findall(tekst)]
    tekst = NOTATKA.sub("", tekst)
    tekst = tekst.replace("****", "")              # puste pogrubienie po wycięciu notatki
    return tekst.strip()


def _komorka(kom, info):
    return " ".join(t for t in (tekst_md(b["paragraph"], info) for b in kom.get("content", [])
                                if "paragraph" in b) if t).replace("|", "\\|")


def tabela_md(tabela, info):
    wiersze = [[_komorka(k, info) for k in w["tableCells"]] for w in tabela["tableRows"]]
    if not wiersze:
        return ""
    # nagłówek tabeli jest w Docs pogrubiony, w Markdown wyróżnia go sama składnia
    wiersze[0] = [re.sub(r"^\*\*(.*)\*\*$", r"\1", k) for k in wiersze[0]]
    linie = ["| " + " | ".join(wiersze[0]) + " |",
             "| " + " | ".join("---" for _ in wiersze[0]) + " |"]
    linie += ["| " + " | ".join(w) + " |" for w in wiersze[1:]]
    return "\n".join(linie)


def rodzaj_listy(lista, poziom):
    """„numerowana”, „punktor” albo „zadania” (lista kontrolna z polami wyboru)."""
    try:
        p = lista["listProperties"]["nestingLevels"][poziom]
    except (KeyError, IndexError, TypeError):
        return "punktor"
    if p.get("glyphType") not in (None, "GLYPH_TYPE_UNSPECIFIED", "NONE"):
        return "numerowana"
    # lista kontrolna: typ nieokreślony, ale z formatem i bez symbolu punktora;
    # sam typ nieokreślony bez formatu (zdarza się po wklejeniu) to zwykły punktor
    if "glyphSymbol" not in p and "glyphFormat" in p and p.get("glyphType") == "GLYPH_TYPE_UNSPECIFIED":
        return "zadania"
    return "punktor"


def odhaczony(akapit):
    """Zadanie z listy kontrolnej jest odhaczone, gdy cały tekst jest przekreślony."""
    runy = [el["textRun"] for el in akapit.get("elements", [])
            if el.get("textRun", {}).get("content", "").strip()]
    return bool(runy) and all(r.get("textStyle", {}).get("strikethrough") for r in runy)


def karta_md(karta):
    """Zwraca (markdown, info). info = {"podswietlone": [...], "notatki": [...], "pominiete": {...}}."""
    dt = karta["documentTab"]
    listy = dt.get("lists", {})
    info = {"podswietlone": [], "notatki": [], "pominiete": {}}
    bloki = []            # (rodzaj, tekst); rodzaj „li:<listId>” dla punktów
    licznik = {}
    for e in dt["body"]["content"]:
        for k in e:
            if k not in ZNANE_BLOKI:
                info["pominiete"][k] = info["pominiete"].get(k, 0) + 1
        if "table" in e:
            bloki.append(("tabela", tabela_md(e["table"], info)))
            continue
        a = e.get("paragraph")
        if not a:
            continue
        for el in a.get("elements", []):
            for k in el:
                if k not in ZNANE_ELEMENTY:
                    info["pominiete"][k] = info["pominiete"].get(k, 0) + 1
        tekst = tekst_md(a, info)
        if not tekst:
            continue
        styl = a.get("paragraphStyle", {}).get("namedStyleType", "NORMAL_TEXT")
        if styl == "TITLE":
            bloki.append(("naglowek", "# " + tekst))
        elif styl.startswith("HEADING_"):
            bloki.append(("naglowek", "#" * int(styl[8:]) + " " + re.sub(r"^\*\*(.*)\*\*$", r"\1", tekst)))
        elif "bullet" in a:
            lid = a["bullet"].get("listId")
            poz = a["bullet"].get("nestingLevel", 0)
            rodzaj = rodzaj_listy(listy.get(lid), poz)
            if rodzaj == "numerowana":
                licznik[(lid, poz)] = licznik.get((lid, poz), 0) + 1
                znak = f"{licznik[(lid, poz)]}. "
            elif rodzaj == "zadania":
                znak = "- [x] " if odhaczony(a) else "- [ ] "
            else:
                znak = "- "
            bloki.append((f"li:{lid}", "  " * poz + znak + tekst.replace("\n", " ")))
        else:
            bloki.append(("tekst", tekst))
    out = []
    for i, (rodzaj, t) in enumerate(bloki):
        if i and not (rodzaj.startswith("li:") and bloki[i - 1][0] == rodzaj):
            out.append("")
        out.append(t)
    return "\n".join(out).rstrip() + "\n", info
