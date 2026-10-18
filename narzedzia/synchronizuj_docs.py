#!/usr/bin/env python3
"""Synchronizacja raportów z sesji: Google Docs -> repo, z ochroną przed nadpisaniem.

Raporty powstają i są poprawiane WYŁĄCZNIE w Google Docs (dokument „Spalony Gulasz
w Szemrotach”, karty „Raport sesja RRRRMMDD”). Repo to kopia z historią. Ten skrypt
porównuje JSON dokumentu (wynik narzędzia Google Docs read_doc) z raportami w repo,
pokazuje tylko zmiany i zapisuje je do repo, ale tylko tam, gdzie nie zniszczy
niczego, czego nie ma w Docs. Metoda przeniesiona z repo Moretti.

Polecenia:
  raport  DOK.json             stan każdego raportu (jedna linijka na raport)
  pokaz   DOK.json 3 [1 …]     różnice w podanych raportach (numer sesji)
  zapisz  DOK.json 3 [1 …]     zapis bezpiecznych zmian z Docs do repo
  zapisz  DOK.json wszystko    jw. dla wszystkich raportów
  sprawdz                      czy pliki raportów w repo są dokładnie takie, jak po
                               ostatniej synchronizacji (bez JSON-a; uruchamiać przed
                               każdym commitem, robi to też CI)
  inicjuj DOK.json [--baza C]  jednorazowo: uznaj pliki (obecne albo z commitu C,
                               jeśli tam były ostatnio zgodne z Docs) za punkt wyjścia

Stan po każdej synchronizacji (sha256 każdego pliku, rewizja Docs, czas pobrania
JSON-a) trzymany jest w narzedzia/stan_synchronizacji.json. Statusy:
  BEZ ZMIAN         – Docs i repo to samo
  ZMIANY W DOCS     – plik w repo nietknięty od synchronizacji; zapis bezpieczny
  NOWY              – raport jest tylko w Docs; zapis bezpieczny
  ZGODNE            – plik w repo zmieniony, ale tak samo jak w Docs; zapis odświeża stan
  TYLKO W REPO      – ktoś zmienił plik w repo, w Docs tego nie ma; ZAPIS ZABLOKOWANY
  KONFLIKT          – zmiany i w repo, i w Docs; ZAPIS ZABLOKOWANY
  USUNIĘTY W REPO   – plik skasowany w repo poza synchronizacją; ZAPIS ZABLOKOWANY
  BRAK W DOCS       – raport zniknął z Docs; skrypt nigdy nie usuwa plików

Zmiany Claude'a w Docs są podświetlone (kolor tła); podświetlenie zdejmuje ten,
kto przeczytał. Niczego nie wstrzymuje i nie przechodzi do repo. Wyjaśnienia
[Claude: …] zostają tylko w Docs: przy konwersji są wycinane, a sprawdz zgłasza
je jako błąd, gdyby trafiły do pliku raportu.

Zapis odmawia też, gdy zmienia się naraz ponad połowa raportów (przy co najmniej
4; może to znaczyć zmianę formatu u Google; po obejrzeniu: --masowo), gdy JSON nie
ma oczekiwanej struktury, oraz gdy JSON jest starszy niż ostatnia synchronizacja
(np. stary plik z wcześniejszej rozmowy) – wtedy trzeba pobrać dokument ponownie.
Podawaj ścieżkę do pliku z wyniku read_doc bez kopiowania go (czas pliku = czas
pobrania). Zasady konwersji: narzedzia/konwersja.py; wzorzec prawdziwego JSON-a
z Docs i oczekiwany wynik: narzedzia/wzorce/.
"""
import argparse
import datetime as dt
import difflib
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from konwersja import NOTATKA, karta_md  # noqa: E402

REPO = Path(__file__).resolve().parent.parent

# ID dokumentu -> (folder z raportami, początek tytułu karty z raportem)
DOKUMENTY = {
    "1bGy01ChiY076OkPJLDuMLOvCQeMK6_wA4XIFyr_Car0": ("raporty", "Raport sesja"),
}
WZORZEC_PLIKU = "sesja-[0-9][0-9].md"
NR_Z_TYTULU = re.compile(r"raport z sesji\s+(\d+)", re.I)


# ---------------------------------------------------------------- Docs -> MD

def wszystkie_karty(karty):
    for k in karty:
        yield k
        yield from wszystkie_karty(k.get("childTabs", []))


def raporty_z_dokumentu(dok, prefiks):
    """{numer: (nazwa_pliku, markdown, info, tytuł_karty)} – karty z raportami."""
    karty = [k for k in wszystkie_karty(dok["tabs"])
             if k["tabProperties"]["title"].startswith(prefiks)]
    if not karty:
        nazwy = ", ".join(k["tabProperties"]["title"] for k in wszystkie_karty(dok["tabs"]))
        sys.exit(f"Nie ma kart „{prefiks} …”. Karty w dokumencie: {nazwy}")
    karty.sort(key=lambda k: k["tabProperties"]["title"])     # RRRRMMDD = kolejność sesji
    wynik = {}
    for i, k in enumerate(karty, 1):
        md, info = karta_md(k)
        m = NR_Z_TYTULU.search(md.split("\n", 1)[0])
        nr = int(m.group(1)) if m else i
        if nr in wynik:
            sys.exit(f"ODMOWA: dwie karty z raportem z sesji {nr}: "
                     f"„{wynik[nr][3]}” i „{k['tabProperties']['title']}”.")
        wynik[nr] = (f"sesja-{nr:02d}.md", md, info, k["tabProperties"]["title"])
    return wynik


# ------------------------------------------------------------- porównywanie

def akapity(md):
    return [l.rstrip() for l in md.splitlines() if l.strip()]


def pokrewne(x, y):
    return difflib.SequenceMatcher(None, x, y, autojunk=False).ratio() > 0.5


def pary(stare, nowe):
    """Łączy w pary akapity zmienione „w miejscu”; reszta to usunięte i dodane."""
    wynik, j = [], 0
    for x in stare:
        k = next((k for k in range(j, len(nowe)) if pokrewne(x, nowe[k])), None)
        if k is None:
            wynik.append((x, None))
            continue
        wynik += [(None, y) for y in nowe[j:k]] + [(x, nowe[k])]
        j = k + 1
    return wynik + [(None, y) for y in nowe[j:]]


def bloki(stary_md, nowy_md):
    s, n = akapity(stary_md), akapity(nowy_md)
    sm = difflib.SequenceMatcher(None, s, n, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "equal":
            yield i1, j1, pary(s[i1:i2], n[j1:j2])


def roznica_slow(stary, nowy):
    s, n = stary.split(), nowy.split()
    ops = difflib.SequenceMatcher(None, s, n, autojunk=False).get_opcodes()
    kawalki = []
    for i, (tag, i1, i2, j1, j2) in enumerate(ops):
        if tag == "equal":
            pierwszy, ostatni, fr = i == 0, i == len(ops) - 1, s[i1:i2]
            if pierwszy and ostatni:
                kawalki += fr
            elif pierwszy:
                kawalki += (["…"] if len(fr) > 6 else []) + fr[-6:]
            elif ostatni:
                kawalki += fr[:6] + (["…"] if len(fr) > 6 else [])
            elif len(fr) > 12:
                kawalki += fr[:6] + ["…"] + fr[-6:]
            else:
                kawalki += fr
            continue
        if i2 > i1:
            kawalki.append("[-" + " ".join(s[i1:i2]) + "-]")
        if j2 > j1:
            kawalki.append("{+" + " ".join(n[j1:j2]) + "+}")
    return " ".join(kawalki)


def opis_zmian(stary_md, nowy_md):
    out = []
    for i1, j1, ps in bloki(stary_md, nowy_md):
        out.append(f"@@ akapit {i1 + 1} (repo) / {j1 + 1} (Docs)")
        for x, y in ps:
            if x and y:
                out.append("~ " + roznica_slow(x, y))
            elif x:
                out.append("- " + x)
            else:
                out.append("+ " + y)
    return out


def statystyka(stary_md, nowy_md):
    zm = us = do = 0
    for _, _, ps in bloki(stary_md, nowy_md):
        for x, y in ps:
            zm += bool(x and y)
            us += bool(x and not y)
            do += bool(y and not x)
    return zm, us, do


# ------------------------------------------------------------ stan i git

PLIK_STANU = "narzedzia/stan_synchronizacji.json"


def sha(tekst):
    return hashlib.sha256(tekst.encode("utf-8")).hexdigest()


def czas(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat(timespec="seconds")


def wczytaj_stan(repo):
    p = repo / PLIK_STANU
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def zapisz_stan(repo, stan):
    (repo / PLIK_STANU).write_text(json.dumps(stan, ensure_ascii=False, indent=2, sort_keys=True)
                                   + "\n", encoding="utf-8")


def wersja_bazowa(repo, sciezka, hash_):
    """Treść pliku z historii gita o danym sha256 (wersja z ostatniej synchronizacji)."""
    rel = sciezka.relative_to(repo).as_posix()
    try:
        commity = subprocess.run(["git", "-C", str(repo), "log", "--format=%H", "-n", "200",
                                  "--", rel], capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    for c in commity.stdout.split():
        r = subprocess.run(["git", "-C", str(repo), "show", f"{c}:{rel}"], capture_output=True)
        if r.returncode == 0:
            t = r.stdout.decode("utf-8", "replace")
            if sha(t) == hash_:
                return t
    return None


def pliki_repo(folder):
    return {int(p.name[6:8]): p for p in sorted(folder.glob(WZORZEC_PLIKU))}


# ------------------------------------------------------------ klasyfikacja

BEZPIECZNE = {"BEZ ZMIAN", "ZMIANY W DOCS", "NOWY", "ZGODNE"}


class Raport:
    def __init__(self, nr, plik, docs, plik_repo, hash_stanu, repo):
        self.nr, self.plik, self.docs = nr, plik, docs     # docs: (nazwa, md, info, karta) albo None
        self.repo_md = plik_repo.read_text(encoding="utf-8") if plik_repo else None
        self.hash_stanu, self._repo, self._baza = hash_stanu, repo, False
        self.status = self._status()

    @property
    def docs_md(self):
        return self.docs[1] if self.docs else None

    @property
    def podswietlone(self):
        return self.docs[2]["podswietlone"] if self.docs else []

    @property
    def notatki(self):
        return self.docs[2]["notatki"] if self.docs else []

    def zmieniony_w_repo(self):
        if self.repo_md is None:
            return self.hash_stanu is not None
        return self.hash_stanu != sha(self.repo_md)

    def baza(self):
        if self._baza is False:
            self._baza = (wersja_bazowa(self._repo, self.plik, self.hash_stanu)
                          if self.hash_stanu else None)
        return self._baza

    def _status(self):
        if self.docs is None:
            return "BRAK W DOCS"
        if self.repo_md is None and self.hash_stanu is None:
            return "NOWY"
        rowne = self.repo_md is not None and self.repo_md == self.docs_md
        if not self.zmieniony_w_repo():
            return "BEZ ZMIAN" if rowne else "ZMIANY W DOCS"
        if rowne:
            return "ZGODNE"
        b = self.baza()
        if b is not None and b == self.docs_md:
            return "TYLKO W REPO"
        return "KONFLIKT"


def raporty(dok, prefiks, folder, stan_folderu, repo):
    docs = raporty_z_dokumentu(dok, prefiks)
    pliki = pliki_repo(folder)
    hashe = stan_folderu.get("pliki", {})
    znane = {int(n[6:8]): n for n in hashe}
    wynik = {}
    for nr in sorted(set(docs) | set(pliki) | set(znane)):
        p = pliki.get(nr)
        nazwa = p.name if p else znane.get(nr) or docs[nr][0]
        r = Raport(nr, folder / nazwa, docs.get(nr), p, hashe.get(nazwa), repo)
        if p is None and nr in znane and r.docs is not None:
            r.status = "USUNIĘTY W REPO"
        wynik[nr] = r
    return wynik


def ostrzezenia_formatu(dok, prefiks):
    pominiete = {}
    for nr, (_, _, info, _) in raporty_z_dokumentu(dok, prefiks).items():
        for k, n in info["pominiete"].items():
            pominiete[f"{k} (sesja {nr})"] = n
    return [f"{k}×{n}" for k, n in sorted(pominiete.items())]


# ------------------------------------------------------------ polecenia

def ostrzezenie_o_wieku(sciezka, stan_folderu):
    pobrano = stan_folderu.get("pobrano")
    if pobrano and czas(sciezka.stat().st_mtime) < pobrano:
        return (f"JSON pobrano {czas(sciezka.stat().st_mtime)}, a raporty zsynchronizowano "
                f"z pobrania {pobrano}. To starsza wersja dokumentu – pobierz go ponownie.")
    return None


def polecenie_raport(rs, stan_folderu, sciezka):
    w = ostrzezenie_o_wieku(sciezka, stan_folderu)
    if w:
        print("  UWAGA: " + w)
    bez = []
    for nr, r in rs.items():
        if r.status == "BEZ ZMIAN":
            bez.append(nr)
            continue
        opis = r.plik.name
        if r.docs:
            opis += f" ← „{r.docs[3]}”"
        if r.status == "NOWY":
            opis += f"  ({len(akapity(r.docs_md))} akapitów)"
        elif r.status in ("ZMIANY W DOCS", "TYLKO W REPO", "KONFLIKT") and r.repo_md is not None:
            zm, us, do = statystyka(r.repo_md, r.docs_md)
            opis += f": ~{zm} zmienionych, -{us} usuniętych, +{do} dodanych (repo → Docs)"
        if r.status != "BRAK W DOCS" and (r.podswietlone or r.notatki):
            opis += (f"  [podświetlone: {len(r.podswietlone)} fragm."
                     + (f", notatki [Claude: …] wycinane: {len(r.notatki)}" if r.notatki else "") + "]")
        znak = "  " if r.status in BEZPIECZNE else "!!"
        print(f"{znak}{nr:2d}  {r.status:<16} {opis}")
    print(f"  bez zmian: {zakresy(bez) or '—'}")
    blokady = [nr for nr, r in rs.items() if r.status not in BEZPIECZNE]
    if blokady:
        print(f"  zablokowane do zapisu: {zakresy(blokady)} (szczegóły: pokaz)")


def polecenie_pokaz(rs, numery):
    for nr in numery:
        r = rs.get(nr)
        if r is None:
            print(f"\n## {nr}: nie ma takiego raportu ani w Docs, ani w repo")
            continue
        print(f"\n## {nr}. {r.plik.name}  [{r.status}]")
        if r.podswietlone:
            print("--- podświetlone w Docs (zmiany do przeczytania; nie wstrzymują synchronizacji):")
            print("\n".join("* " + (x if len(x) < 160 else x[:150] + " …") for x in r.podswietlone))
        if r.notatki:
            print("--- notatki [Claude: …] w Docs (do repo nie trafiają):")
            print("\n".join("* " + x for x in r.notatki))
        if r.status in ("TYLKO W REPO", "KONFLIKT"):
            b = r.baza()
            if b is None:
                print("(brak wersji z ostatniej synchronizacji w historii gita – porównuję repo "
                      "z Docs; dłuższa historia: git fetch --depth=200 origin main)")
            else:
                print("--- co zmieniono w REPO od ostatniej synchronizacji "
                      "(tego nie ma w Docs, trzeba przenieść):")
                print("\n".join(opis_zmian(b, r.repo_md or "")) or "nic")
                if r.status == "KONFLIKT":
                    print("--- co zmieniono w DOCS od ostatniej synchronizacji:")
                    print("\n".join(opis_zmian(b, r.docs_md)) or "nic")
                continue
        zmiany = opis_zmian(r.repo_md or "", r.docs_md or "")
        print("\n".join(zmiany) if zmiany else "bez zmian")


def polecenie_zapisz(rs, numery, a, repo, stan, folder, dok, sciezka):
    st = stan.setdefault(folder, {})
    if "pliki" not in st:
        sys.exit(f"Brak stanu synchronizacji dla {folder}/. Najpierw: inicjuj DOK.json")
    w = ostrzezenie_o_wieku(sciezka, st)
    if w and not a.stary_json:
        sys.exit("ODMOWA: " + w)
    istniejace = [r for r in rs.values() if r.repo_md is not None]
    zmienione = [r for r in istniejace if r.nr in numery and r.status == "ZMIANY W DOCS"]
    if len(istniejace) >= 4 and len(zmienione) > len(istniejace) / 2 and not a.masowo:
        sys.exit(f"ODMOWA: zmiany w {len(zmienione)} z {len(istniejace)} raportów naraz – "
                 "podejrzanie dużo (zmiana formatu u Google albo w konwersji?). Obejrzyj pokaz; "
                 "jeśli wszystko w porządku, dodaj --masowo.")
    wymuszone = set(a.nadpisz_repo or [])
    zapisane, odmowy = [], []
    for nr in numery:
        r = rs.get(nr)
        if r is None or r.docs is None:
            odmowy.append(f"{nr}: nie ma go w Docs")
            continue
        if r.status not in BEZPIECZNE and nr not in wymuszone:
            odmowy.append(f"{nr} ({r.plik.name}): {r.status} – najpierw przenieś zmiany z repo "
                          f"do Docs (pokaz {nr}) albo wymuś --nadpisz-repo {nr}")
            continue
        if r.repo_md != r.docs_md:
            r.plik.parent.mkdir(parents=True, exist_ok=True)
            r.plik.write_text(r.docs_md, encoding="utf-8")
            zapisane.append(f"{folder}/{r.plik.name}")
        st["pliki"][r.plik.name] = sha(r.docs_md)
    st.update({
        "dokument": dok.get("documentId"),
        "rewizja": dok.get("revisionId"),
        "pobrano": max(st.get("pobrano", ""), czas(sciezka.stat().st_mtime)),
        "zsynchronizowano": czas(dt.datetime.now().timestamp()),
    })
    zapisz_stan(repo, stan)
    for z in zapisane:
        print(f"  zapisano {z}")
    if not zapisane:
        print("  nic do zapisania")
    for o in odmowy:
        print(f"!!ODMOWA {o}")
    if odmowy:
        sys.exit(1)


def polecenie_sprawdz(repo, stan):
    bledy = []
    if not stan:
        bledy.append("brak stanu synchronizacji (narzedzia/stan_synchronizacji.json)")
    for folder, st in sorted(stan.items()):
        znane = st.get("pliki", {})
        obecne = {p.name: p for p in (repo / folder).glob(WZORZEC_PLIKU)}
        for nazwa, h in sorted(znane.items()):
            if nazwa not in obecne:
                bledy.append(f"{folder}/{nazwa}: usunięty poza synchronizacją")
            elif sha(obecne[nazwa].read_text(encoding="utf-8")) != h:
                bledy.append(f"{folder}/{nazwa}: zmieniony poza synchronizacją z Google Docs")
        for nazwa in sorted(set(obecne) - set(znane)):
            bledy.append(f"{folder}/{nazwa}: dodany poza synchronizacją z Google Docs")
        for nazwa, plik in sorted(obecne.items()):
            if NOTATKA.search(plik.read_text(encoding="utf-8")):
                bledy.append(f"{folder}/{nazwa}: zawiera notatkę [Claude: …], która miała zostać w Docs")
    if bledy:
        print("Raporty różnią się od stanu ostatniej synchronizacji:")
        print("\n".join("  " + b for b in bledy))
        print("Raporty zmienia się tylko w Google Docs i przenosi skryptem (zapisz). "
              "Patrz README, sekcja „Raporty a Google Docs”.")
        sys.exit(1)
    print(f"OK: raporty zgodne ze stanem synchronizacji ({', '.join(sorted(stan))}).")


def pliki_z_commitu(repo, folder, commit):
    r = subprocess.run(["git", "-C", str(repo), "ls-tree", "--name-only", commit, f"{folder}/"],
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"Nie znam commitu {commit}: {r.stderr.strip()}")
    wynik = {}
    for sciezka in r.stdout.split():
        nazwa = Path(sciezka).name
        if Path(nazwa).match(WZORZEC_PLIKU):
            t = subprocess.run(["git", "-C", str(repo), "show", f"{commit}:{sciezka}"],
                               capture_output=True, check=True).stdout.decode("utf-8")
            wynik[nazwa] = sha(t)
    return wynik


def polecenie_inicjuj(repo, stan, folder, dok, baza=None):
    if "pliki" in stan.get(folder, {}):
        sys.exit(f"{folder}/ ma już stan synchronizacji – inicjuj służy tylko do pierwszego razu.")
    if baza:
        pliki = pliki_z_commitu(repo, folder, baza)
    else:
        pliki = {p.name: sha(p.read_text(encoding="utf-8"))
                 for p in sorted((repo / folder).glob(WZORZEC_PLIKU))}
    stan[folder] = {
        "dokument": dok.get("documentId"),
        "rewizja": None,       # repo nie musi jeszcze odpowiadać żadnej rewizji Docs
        "pobrano": "",
        "zsynchronizowano": czas(dt.datetime.now().timestamp()),
        "pliki": pliki,
    }
    if baza:
        stan[folder]["baza"] = baza
    zapisz_stan(repo, stan)
    print(f"Zapisano stan {folder}/: {len(pliki)} raportów jako punkt wyjścia"
          + (f" (wersje z commitu {baza})." if baza else "."))


def zakresy(liczby):
    out, i = [], 0
    while i < len(liczby):
        j = i
        while j + 1 < len(liczby) and liczby[j + 1] == liczby[j] + 1:
            j += 1
        out.append(str(liczby[i]) if i == j else f"{liczby[i]}–{liczby[j]}")
        i = j + 1
    return ", ".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__)
    ap.add_argument("polecenie", choices=["raport", "pokaz", "zapisz", "sprawdz", "inicjuj"])
    ap.add_argument("argumenty", nargs="*", help="DOK.json i numery sesji")
    ap.add_argument("--nadpisz-repo", type=int, nargs="+", metavar="NR",
                    help="wymuś zapis zablokowanych raportów (zmiany z repo przepadną)")
    ap.add_argument("--masowo", action="store_true",
                    help="pozwól zapisać zmiany w ponad połowie raportów naraz")
    ap.add_argument("--stary-json", action="store_true",
                    help="pozwól zapisać z JSON-a starszego niż ostatnia synchronizacja")
    ap.add_argument("--baza", metavar="COMMIT",
                    help="inicjuj: weź punkt wyjścia z tego commitu zamiast z obecnych plików")
    ap.add_argument("--repo", type=Path, default=REPO, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    repo, stan = a.repo, wczytaj_stan(a.repo)

    if a.polecenie == "sprawdz":
        return polecenie_sprawdz(repo, stan)
    if not a.argumenty:
        ap.error("podaj plik JSON z Google Docs")
    sciezka = Path(a.argumenty[0])
    dane = json.loads(sciezka.read_text(encoding="utf-8"))
    dok = dane.get("content", dane)
    if dok.get("documentId") not in DOKUMENTY:
        sys.exit(f"Nieznany dokument {dok.get('documentId')} – dopisz go do DOKUMENTY w skrypcie.")
    folder, prefiks = DOKUMENTY[dok["documentId"]]
    if a.polecenie == "inicjuj":
        return polecenie_inicjuj(repo, stan, folder, dok, a.baza)
    try:
        pominiete = ostrzezenia_formatu(dok, prefiks)
        rs = raporty(dok, prefiks, repo / folder, stan.get(folder, {}), repo)
    except (KeyError, TypeError, AttributeError, ValueError) as e:
        sys.exit(f"ODMOWA: JSON nie ma oczekiwanej struktury ({type(e).__name__}: {e}). "
                 "Google mógł zmienić format odpowiedzi – sprawdź na wzorcu narzedzia/wzorce/ "
                 "i popraw skrypt, zanim cokolwiek zapiszesz.")
    print(f"„{dok.get('title')}” / karty „{prefiks} …” ↔ {folder}/  "
          f"(rewizja {dok.get('revisionId', '?')[:12]})")
    if pominiete:
        print("  UWAGA: elementy, których konwersja nie przenosi (ich treść nie trafi do repo): "
              + ", ".join(pominiete))
    if a.polecenie == "raport":
        if not stan.get(folder):
            print(f"  UWAGA: {folder}/ nie ma stanu synchronizacji (inicjuj).")
        return polecenie_raport(rs, stan.get(folder, {}), sciezka)
    reszta = a.argumenty[1:]
    numery = (sorted(r for r in rs if rs[r].docs) if reszta == ["wszystko"]
              else [int(x) for x in reszta])
    if not numery:
        ap.error("podaj numery sesji (albo „wszystko”)")
    if a.polecenie == "pokaz":
        return polecenie_pokaz(rs, numery)
    return polecenie_zapisz(rs, numery, a, repo, stan, folder, dok, sciezka)


if __name__ == "__main__":
    main()
