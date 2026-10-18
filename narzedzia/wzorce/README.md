# Wzorce do testów synchronizacji

- `google-docs.json` to **prawdziwy** wycinek odpowiedzi Google Docs (`read_doc`) z 18.10.2026. Ma pełną strukturę API (karty, `startIndex`, style, listy w `lists`), ale tylko wybrane akapity z kart „Ogłoszenie”, „Raport sesja 20260925” i „Raport sesja 20261016”.
- `oczekiwane/` zawiera wynik konwersji tego wycinka, sprawdzony ręcznie (każda linijka zgadza się z raportami w repo albo z tekstem w Docs). Test porównuje go znak po znaku.

Co jest we wzorcu:

| Przypadek | Skąd |
|---|---|
| nagłówki 1–3, linijka z datą i autorem | sesja 1, 3 |
| zwykła lista punktowana | sesja 3 |
| lista o typie nieokreślonym bez formatu (po wklejeniu) – to punktor, nie lista zadań | sesja 1 |
| lista kontrolna (pola wyboru) → `- [ ]` | sesja 3 |
| tabela z pogrubionym wierszem nagłówka | sesja 3 |
| pogrubienie w środku akapitu („Pula: **Tp +2 +2Vr**”) i na początku („**Kamery.**”) | sesja 1, 3 |
| podział strony, karta, która nie jest raportem | sesja 1, Ogłoszenie |

Gdy Google zmieni format odpowiedzi, `synchronizuj_docs.py` odmówi zapisu z komunikatem o strukturze. Pomogą też ostrzeżenie o elementach, których konwersja nie przenosi, i blokada zmiany ponad połowy raportów naraz. Wtedy:

1. pobierz świeży JSON i porównaj jego strukturę z `google-docs.json`,
2. popraw `konwersja.py` albo skrypt,
3. wytnij nowy wzorzec z tymi samymi przypadkami, a `oczekiwane/` zostaw bez zmian; tekst wyniku ma wyjść taki sam.
