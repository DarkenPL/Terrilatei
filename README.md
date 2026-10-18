# Terrilatei
Raporty z sesji

## Spalony Gulasz w Szemrotach

Jesteśmy lokalną komórką Terriletei, agencji, która ubezpiecza i odbudowuje tereny po wojnie i zajmuje się anomaliami „niższego sortu”. Przyjechałyśmy do Szemrot po anonimowym cynku, że pomnik Sowińskiego chodzi nocą do spalonego baru „Gulasz u Mamy”.

### Gdzie jesteśmy po sesji 3

Bar podpalono celowo, żeby zasypać zejście do podziemi. Ida, córka właścicielki, żyje i próbuje rozebrać mur pod pomnikiem i „Gulaszem”. Według niej za murem jest dowód, że jej matka zamurowała ludzi. Za każdym razem, gdy Ida próbuje się przebić, przychodzi Sowiński, a ubytki wypełnia twardy „brąz”.

Stoimy przy tym murze pod ziemią, z Idą i przestraszonym dzieciakiem z młodzieży. Irse nie ma sprzętu, a Fafik uciekł w panice przed czymś, czego nikt inny nie usłyszał. Centrala dała nam 3 dni, zostało ok. 2,5.

Najpilniejsze:

- Co z murem: otwierać teraz czy wrócić przygotowanymi?
- Wyprowadzić Idę i dzieciaka na powierzchnię.
- Porozmawiać z Wiesławą o zamurowanych ludziach.
- Rano: kontener medyczny, wyniki próbek, sprzęt do podziemi.

[![Rzut izometryczny targowiska w Szemrotach](obrazy/targowisko.png)](podsumowanie.md#mapa-targowiska)

**[Pełne podsumowanie sesji 1–3: ustalenia, ludzie, stan drużyny, otwarte wątki](podsumowanie.md)**

### Raporty z sesji

- [Sesja 1](raporty/sesja-01.md) — 25.09.2026: samosąd pod pomnikiem, przesłuchanie Xaviera, nagrania z kamer
- [Sesja 2](raporty/sesja-02.md) — 2.10.2026: Ksenia Radlic, zgliszcza „Gulaszu”, pomnik, telefon z Centrali, stream Idy
- [Sesja 3](raporty/sesja-03.md) — 16.10.2026: podziemia pod termami, drony, Ida i mur pod „Gulaszem”

## Raporty a Google Docs

**Raporty z sesji powstają i są poprawiane tylko w Google Docs**, w dokumencie „Spalony Gulasz w Szemrotach”, po jednej karcie „Raport sesja RRRRMMDD” na sesję. Repo jest kopią z historią. Plików `raporty/sesja-NN.md` nikt nie poprawia ręcznie; zmienia je tylko `narzedzia/synchronizuj_docs.py`. README, `podsumowanie.md` i obrazy edytuje się w repo normalnie. Metoda pochodzi z repo Moretti.

Jak przebiega synchronizacja (robi to Claude):

1. **Pobranie:** łącznik Google Docs `read_doc`. Dokument zapisuje się jako plik JSON i nie trafia do rozmowy.
2. **Raport:** `python3 narzedzia/synchronizuj_docs.py raport DOK.json`, jedna linijka na raport.
3. **Podgląd:** `pokaz DOK.json 3` wypisuje tylko zmienione akapity, a w nich słowo po słowie (`[-usunięte-] {+dodane+}`).
4. **Zapis:** `zapisz DOK.json 3` (albo `wszystko`) zapisuje tylko raporty, przy których zapis jest bezpieczny.
5. **Kontrola i commit:** `sprawdz`, potem commit z plikami raportów **i** `narzedzia/stan_synchronizacji.json`.

Po każdej synchronizacji skrypt zapisuje w `narzedzia/stan_synchronizacji.json` sumę kontrolną (sha256) każdego raportu, rewizję dokumentu i czas pobrania JSON-a. Dzięki temu wie, kto co zmienił:

| Status | Co znaczy | Zapis |
|---|---|---|
| BEZ ZMIAN | Docs i repo to samo | – |
| ZMIANY W DOCS | ktoś pisał w Docs, plik w repo nietknięty od synchronizacji | tak |
| NOWY | raport jest tylko w Docs | tak |
| ZGODNE | plik w repo zmieniony, ale tak samo jak w Docs | tak (odświeża stan) |
| TYLKO W REPO | plik w repo zmieniony poza synchronizacją, a w Docs tego nie ma | **zablokowany** |
| KONFLIKT | zmiany i w repo, i w Docs | **zablokowany** |
| USUNIĘTY W REPO | plik skasowany w repo poza synchronizacją | **zablokowany** |
| BRAK W DOCS | karta zniknęła z Docs | skrypt nigdy nie usuwa plików |

Zablokowany raport: `pokaz` wypisuje, co jest tylko w repo (porównanie z wersją z ostatniej synchronizacji z historii gita). Te zmiany przenosi się do Docs i dopiero potem synchronizuje.

Dodatkowe zabezpieczenia: odmowa zapisu ze starego JSON-a (starszego niż ostatnia synchronizacja), z JSON-a o nieoczekiwanej strukturze i przy zmianie ponad połowy raportów naraz (`--masowo` po obejrzeniu); ostrzeżenie o elementach, których konwersja nie przenosi (obrazki, chipy); **GitHub Actions** uruchamia testy i `sprawdz` przy każdym pushu, więc ręczna zmiana raportu daje czerwony krzyżyk.

Zmiany Claude'a w Docs są **podświetlone** (kolor tła); podświetlenie zdejmuje ten, kto przeczytał. Przy większych zmianach Claude dopisuje za zmianą wyjaśnienie `[Claude: …]`. Do repo nie trafia ani podświetlenie, ani wyjaśnienie.

Konwersja (`narzedzia/konwersja.py`) daje to samo co eksport Google Docs do Markdown: nagłówki `#`, punktory `- `, listy kontrolne `- [ ]`, tabele, pogrubienie, kursywa, linki. Numer pliku bierze z nagłówka „… raport z sesji N”. Testy: `python3 narzedzia/test_synchronizuj_docs.py` (część na prawdziwym wycinku JSON-a z Docs w `narzedzia/wzorce/`).
