# Zasady pracy w repo Terrilatei (dla Claude'a)

Repo to kopia raportów z sesji kampanii „Spalony Gulasz w Szemrotach”, którą prowadzi Darken (MG). Raporty powstają w Google Docs, w dokumencie „Spalony Gulasz w Szemrotach” (ID `1bGy01ChiY076OkPJLDuMLOvCQeMK6_wA4XIFyr_Car0`), po jednej karcie „Raport sesja RRRRMMDD” na sesję. Pełny opis: README.md, sekcja „Raporty a Google Docs”. Metoda przeniesiona z repo Moretti.

## Raporty (`raporty/sesja-NN.md`): nigdy nie edytuj ręcznie

- Źródłem tekstu raportów jest Google Docs. Darken nie poprawia plików raportów w repo i Ty też tego nie robisz: ani Edit/Write, ani sed, ani skrypty jednorazowe.
- Każda zmiana raportu (nowy raport, poprawka, redakcja, ujednolicenie nazw) idzie **do Google Docs**:
  1. świeży `read_doc`,
  2. zapis przez `update_doc` z `writeControl.requiredRevisionId` z tego odczytu,
  3. każda zmiana **podświetlona** (kolor tła, np. żółty); podświetlenie zdejmuje ten, kto przeczytał. Pogrubienie nie jest tu znacznikiem, bo raporty używają go w tekście (pule, nagłówki tabel),
     przy większej zmianie (przebudowane zdanie, dopisany, przesunięty lub usunięty fragment) dodaj zaraz za nią wyjaśnienie `[Claude: …]` (krótko: co i dlaczego); czytający usuwa je, kiedy chce, a skrypt i tak wycina je z tekstu dla repo; drobnych zmian (literówka, kreska) nie objaśniaj,
     nowy raport to nowa karta „Raport sesja RRRRMMDD” z nagłówkiem 1 „Spalony Gulasz w Szemrotach — raport z sesji N” (z niego skrypt bierze numer pliku),
  4. potem synchronizacja do repo (niżej).
- Do repo raporty trafiają tylko przez `narzedzia/synchronizuj_docs.py`. Szkice w toku trzymaj poza repo, w scratchpadzie albo w artefakcie.

## Synchronizacja Docs → repo

```
python3 narzedzia/synchronizuj_docs.py raport  <JSON z read_doc>
python3 narzedzia/synchronizuj_docs.py pokaz   <JSON> 3
python3 narzedzia/synchronizuj_docs.py zapisz  <JSON> 3 | wszystko
python3 narzedzia/synchronizuj_docs.py sprawdz
```

- JSON: wynik `read_doc` zapisany w pliku `tool-results/…` (dokument ma ok. 600 KB). Podaj tę ścieżkę bez kopiowania, bo czas pliku to czas pobrania i skrypt odrzuca JSON starszy niż ostatnia synchronizacja. Nie wczytuj JSON-a do rozmowy.
- **Nie używaj `--nadpisz-repo` bez wyraźnej zgody Darkena.** Status TYLKO W REPO / KONFLIKT / USUNIĘTY W REPO znaczy, że coś w repo nie przeszło przez Docs. Pokaż to (`pokaz`), zaproponuj przeniesienie do Docs i zapytaj.
- Odmowa „nie ma oczekiwanej struktury” albo „podejrzanie dużo” znaczy, że Google mógł zmienić format: nie wymuszaj, porównaj z `narzedzia/wzorce/` (README tam) i zgłoś Darkenowi.
- Podświetlenia nie wstrzymują synchronizacji. Nie zdejmuj ich sam.
- Przed każdym commitem: `python3 narzedzia/synchronizuj_docs.py sprawdz` i `python3 narzedzia/test_synchronizuj_docs.py`. Commit z plikami raportów zawsze razem z `narzedzia/stan_synchronizacji.json`. Ten sam test robi GitHub Actions.

## Commity

- Autor: `Darken <jacek@darken.pl>`, gałąź `main`.
- Nie commituj JSON-ów z Docs ani plików .docx.

## Co edytujesz normalnie w repo

`README.md` (opis „Gdzie jesteśmy”, lista raportów), `podsumowanie.md`, `obrazy/`, `narzedzia/`. Tego skrypt synchronizacji nie dotyka. Inne karty dokumentu (Ogłoszenie, Wprowadzenie do świata, Miejsce i ludzie, Postacie) nie są synchronizowane.
