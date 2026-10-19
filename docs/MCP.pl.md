# Serwer MCP Glyfetti

[English](MCP.md) | **Polski**

Lokalny serwer MCP pozwala asystentowi przeglądać presety i fonty, tworzyć i poprawiać
style, oglądać wyrenderowane podglądy PNG oraz eksportować atlas ZIP lub cały napis PNG.
Używa [oficjalnego SDK Python v2](https://py.sdk.modelcontextprotocol.io/), w zakresie
`>=2.3,<3`. MCP wymaga **Pythona 3.11+**. Zwykłe CLI i edytor w przeglądarce nadal
działają z Pythonem 3.10 bez tego dodatku.

## Instalacja

W katalogu repozytorium, w środowisku Pythona 3.11+:

```bash
python -m pip install -e ".[mcp]"
```

Możesz też zainstalować lokalną paczkę wheel z dodatkiem MCP. Polecenie
`python -m pip install "glyfetti[mcp]"` zadziała, gdy dana wersja będzie dostępna
w używanym indeksie pakietów. Zwykła instalacja nie pobiera SDK MCP.

## Podłączenie klienta

Wygeneruj konfigurację tym Pythonem, w którym zainstalowano Glyfetti i dodatek:

```bash
python -m glyfetti.cli mcp --output-dir ./glyfetti-output --print-config
```

Skopiuj wpis serwera `glyfetti` do ustawień MCP swojego klienta. Kontener `mcpServers`
jest używany m.in. przez Claude Desktop i Cursor; inne programy mogą zapisywać tę
samą komendę i argumenty w innym formacie. Generator wpisuje bieżący interpreter
i bezwzględną ścieżkę eksportów, więc nie trzeba ustawiać katalogu roboczego.
Ogólny szablon jest w [examples/mcp-config.json](../examples/mcp-config.json).

Ręczne uruchomienie serwera:

```bash
python -m glyfetti.cli mcp --output-dir ./glyfetti-output
```

Proces czeka bez komunikatu na wiadomości MCP przez **stdio**. Nie jest to adres HTTP;
zwykle klient sam uruchamia i zamyka proces. Serwer nie wymaga klucza API, abonamentu
modelu ani sieciowego renderera. Diagnostyka trafia na stderr, a stdout przenosi
protokół. Nie dodawaj banerów tekstowych przed komendą startową.

## Narzędzia

| Narzędzie | Zastosowanie |
|---|---|
| `list_presets` | Lista 12 dołączonych stylów. |
| `get_preset` | Pełny preset z bezwzględną ścieżką do fontu. |
| `list_fonts` | Sześć aliasów fontów, ścieżki i zakresy osi zmiennych. |
| `check_font` | Natywna obsługa znaków; budowanie może złożyć polskie znaki. |
| `expand_style` | Walidacja stylu prostego/mieszanego/surowego i zwrot pełnych ustawień. |
| `preview_style` | Obraz PNG i metryki w jakości roboczej, bez tworzenia katalogu eksportu. |
| `export_style` | Atlas ZIP lub przezroczysty napis PNG w pełnej jakości oraz JSON stylu. |
| `analyze_reference_image` | Analiza lokalnego PNG/JPG: gradient, przybliżony obrys i edytowalny styl JSON (parametry `image`, `style`). |

Oba narzędzia renderujące przyjmują `mode: "atlas"` albo `mode: "title"` i opcjonalne
pole `text`. Rzeczywiste znaki nowej linii tworzą kolejne wiersze. Tekst zastępuje
`preview`, a jego znaki są dołączane do eksportowanego atlasu. Własny font można
wskazać ścieżką bezwzględną; względne są liczone od katalogu roboczego serwera.
Aliasy dołączonych fontów działają w stylach prostych niezależnie od katalogu.

Przykładowe argumenty narzędzia:

```json
{
  "style": {
    "name": "victory",
    "simple": { "palette": "gold", "shine": 0.7, "depth_3d": 0.6 }
  },
  "mode": "title",
  "text": "LEVEL COMPLETE!"
}
```

Najpierw użyj `preview_style`, dopracuj parametry, następnie wywołaj `export_style`.
Serwer korzysta z istniejącego renderera Glyfetti. Nie interpretuje sam języka
naturalnego — to asystent dobiera parametry stylu.

## Pliki i zasoby

Każdy udany eksport trafia do nowego katalogu pod `--output-dir`, nazwanego
32-znakowym identyfikatorem. Poprzednie eksporty nie są nadpisywane. Napis to
`title.png` i `style.json`, a atlas to `atlas.zip` i `style.json`. ZIP zawiera PNG,
metryki BMFont/Unity, podglądy i raport budowania. PNG napisu ma przezroczyste tło.

Narzędzie zwraca ścieżki lokalne, rozmiary plików, typy MIME, URI zasobów oraz raport
z brakującymi znakami. Klient MCP może odczytać te same dane przez:

- `glyfetti://styles/schema` — pełny JSON Schema stylów.
- `glyfetti://exports/{export_id}/style.json` — surowy styl do edycji.
- `glyfetti://exports/{export_id}/title.png` — zapisany obraz napisu.
- `glyfetti://exports/{export_id}/atlas.zip` — zapisany atlas.

Szablony zasobów udostępniają tylko znane nazwy plików w skonfigurowanym katalogu
eksportów. Pliki pozostają po rozłączeniu klienta; niepotrzebne katalogi usuń ręcznie.
Poprawione fonty korzystają z cache CLI; podgląd może go uzupełniać. Fonty nie są
kopiowane do eksportów. Zapisane style zachowują lokalne ścieżki, które trzeba
zmienić po przeniesieniu na inny komputer.

## Weryfikacja

Po instalacji dodatku:

```bash
python -m pytest tests/test_mcp.py tests/test_mcp_optional.py -q
```

Testy łączą klienta SDK z serwerem w pamięci oraz przez rzeczywisty proces stdio.
Sprawdzają narzędzia, podglądy, eksport, odczyt zasobów, błędy i negocjację nowych
oraz starszych klientów. Python 3.10 sprawdza komunikat o opcjonalnym środowisku
i uruchamia zwykłe testy bez SDK. Test symlinków działa tam, gdzie system pozwala je
tworzyć. Do testów protokołu nie potrzeba konta w aplikacji asystenta.
