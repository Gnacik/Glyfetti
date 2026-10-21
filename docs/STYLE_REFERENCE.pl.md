# Glyfetti – opis stylów i parametrów

🌐 [English](STYLE_REFERENCE.md) | **Polski**

> Wersja dokumentu: 0.1.4. Styl prosty i surowy działają z atlasem oraz eksportem całego napisu do PNG.

Styl to jeden plik JSON. Glyfetti renderuje każdy znak fontu przez ten sam stos warstw
i zapisuje atlas PNG + metryki (BMFont `.fnt`, JSON dla Unity/TMP) + podgląd.

Styl można pisać na dwóch poziomach:

| Poziom | Dla kogo | Liczba parametrów |
|---|---|---|
| **Prosty** | ludzie, czat przez MCP, suwaki w web UI | ok. 12 „pokręteł” |
| **Surowy** | precyzyjne dopieszczanie, pełna kontrola | wszystkie warstwy osobno |

Styl prosty jest automatycznie rozwijany w surowy. Jeśli w pliku są oba poziomy,
parametry surowe nadpisują to, co wyliczył poziom prosty.

---

## 1. Stos warstw

Każdy znak jest rysowany od spodu w tej kolejności:

```
1. shadow   – cień / poświata (może być rozmyty, przesunięty)
2. extrude  – twarda „podstawa” POZA obrysem (styl naklejki)
3. outline  – obrys; obejmuje literę RAZEM z bokiem 3D
4. side     – bok litery (grubość 3D), POD obrysem
5. fill     – wypełnienie przodu litery gradientem
6. bevel    – wypukłość: rozjaśnienie i przyciemnienie krawędzi
7. gloss    – miękki połysk w górnej części litery
8. spray    – ziarno sprayu i rozpylone kropki wokół krawędzi
```

Każdą warstwę poza `outline` i `fill` można wyłączyć przez `"enabled": false` albo pominąć.

**Jednostki:** wszystkie odległości są w pikselach **docelowego atlasu** (nie superpróbkowania).
Kolory to zapis HEX `#RRGGBB`. Krycie (`opacity`) i siły (`*_strength`) mają zakres 0–1.

---

## 2. Styl prosty

Ustawienia wysokiego poziomu umieść w sekcji `simple`. Parametry surowego renderera
pozostają na najwyższym poziomie. Wymagane są tylko `name` i `simple`; domyślny font
to dołączony Titan One, rozmiar 90, ze znakami łacińskimi, polskimi, cyframi i interpunkcją.

```json
{
  "name": "treasure_gold",
  "font": "Titan One",
  "simple": {
    "base_color": "#F5B845",
    "outline": "dark",
    "outline_width": "medium",
    "depth_3d": 0.6,
    "shadow": "soft",
    "shine": 0.4,
    "glow": null,
    "width": 0.78,
    "weight": 0,
    "playful": 0.3,
    "spacing": -5
  },
  "outline": { "width": 5 }
}
```

Szerokość obrysu na najwyższym poziomie nadpisuje wygenerowaną, zachowując kolor.
Obiekty łączą się rekurencyjnie; tablice, wartości skalarne i `null` zastępują wartości
wygenerowane. Jawne pola `enabled` również mają pierwszeństwo. Istniejące style surowe
zachowują wartości. Rozwinięcie jest deterministyczne i nie nadpisuje pliku źródłowego.

| Pole w `simple` | Typ / zakres | Domyślnie | Wynik |
|---|---|---|---|
| `base_color` | `#RRGGBB` | brak | własna paleta; ma pierwszeństwo przed `palette` |
| `palette` | gold, cream, candy, mint, ice, fire, magic, wood, silver | gold | gotowe kolory wypełnienia, boku i obrysu |
| `outline` | dark / light / none / HEX | dark | kolor obrysu; none zeruje szerokość |
| `outline_width` | thin / medium / thick lub 0–40 px | medium | nazwy: 2.5/4/6 px dla size 100, skalowane z rozmiarem; liczby to piksele końcowe |
| `depth_3d` | 0–1 | 0.5 | do 10 px dla size 100, skalowane z rozmiarem i ograniczone do 40 px |
| `shadow` | none / soft / hard / long | soft | rodzaj cienia |
| `shine` | 0–1 | 0.4 | oświetlenie bevel i połysk; zero wyłącza oba |
| `glow` | null / HEX | null | zastępuje cień wyśrodkowaną poświatą, także gdy shadow to none |
| `width` | 0.5–1.5 | 1 | `condense` |
| `weight` | 0–6 px | 0 | `embolden`; osie fontu ustawia osobne pole `variation` |
| `playful` | 0–1 | 0 | deterministyczny obrót i przesunięcie liter |
| `spacing` | −512–512 px | 0 | `tracking` |

Dla własnego koloru gradient miesza kolor bazowy z bielą w proporcjach 70%, 30%, 0%.
Bok jest mieszany z czernią w 20% i 50%, a ciemny obrys w 80%. Są to bezpośrednie
mieszanki kanałów sRGB, bez konwersji do przestrzeni o równomiernej jasności percepcyjnej.
Nazwane palety zachowują dokładne kolory z tabeli, w tym pięć punktów gradientu srebrnego.

Aliasy dołączonych fontów: `Titan One`, `Grandstander`, `Baloo 2`, `Dosis`, `Chewy`, `Sniglet`.
Inna wartość `font` jest zwykłą ścieżką. Pola `size`, `chars`, `preview`, `variation`,
`title` oraz opcje eksportu pozostają na najwyższym poziomie.

```bash
glyfetti build examples/simple-mint.json --preview-only
glyfetti title examples/simple-mint.json --text "Victory!" -o victory.png
glyfetti expand examples/simple-mint.json -o expanded.json
```

`expand` zapisuje zwalidowany styl surowy i zamienia ścieżkę fontu na bezwzględną;
bez `-o` wypisuje JSON na standardowe wyjście. Nie poprawia fontu — składanie znaków
pozostaje operacją wykonywaną podczas budowania. Kreator koloru i panel JSON w edytorze
przyjmują styl prosty i rozwijają go do ustawień surowych. Zapis JSON i ZIP atlasu
zawierają rozwiniętą postać. Pliki źródłowe pozostają bez zmian. Po przeniesieniu stylu
rozwiniętego na inny komputer trzeba zaktualizować bezwzględną ścieżkę fontu.

---

## 3. Styl surowy – pełna lista parametrów

### 3.1 Ogólne

| Parametr | Typ | Domyślnie | Opis |
|---|---|---|---|
| `name` | string | **wymagany** | nazwa stylu, nazwa plików wynikowych |
| `description` | string | – | opis wyświetlany w galerii i w MCP |
| `font` | ścieżka | **wymagany** | plik TTF/OTF, względnie do pliku stylu |
| `variation` | lista liczb lub obiekt | – | osie fontu zmiennego, np. `{"wght": 800, "wdth": 75}` |
| `size` | px | **wymagany** | rozmiar fontu w atlasie; nie powiększaj tekstu w grze powyżej tej wartości |
| `supersample` | 1–4 | 3 | renderowanie w N× większej skali i zmniejszenie (gładkie krawędzie, ale wolniej) |
| `chars` | string | **wymagany**, chyba że jest `charset` | zestaw znaków do atlasu (duplikaty i spacje są pomijane, spacja jest dodawana zawsze) |
| `charset` | nazwa lub lista | – | nazwane zestawy dopisywane do `chars`: `ascii`, `latin1`, `latin-ext-a`, `cyrillic`, `polish`, `font` (cała cmap fontu, maks. 4096 znaków) |
| `atlas_width` | px | 1024 | szerokość atlasu; wysokość dobierana jako potęga 2 |
| `max_atlas_size` | px | 8192 | maksymalna szerokość i wysokość atlasu; przekroczenie limitu zgłasza błąd |
| `atlas_packing` | `maxrects` / `shelf` | `maxrects` | kompaktowe pakowanie bez obrotu z wariantem awaryjnym w rzędach |
| `kerning` | bool | `true` | eksport poziomych korekt par i ich użycie w podglądzie |
| `kerning_script` | tag OpenType | `latn` | skrypt języka domyślnego dla GPOS kern; wariant awaryjny DFLT |
| `fnt_format` | `text` / `xml` / `binary` | `text` | wariant AngelCode BMFont `.fnt` (binary = wersja 3); CLI `--fnt-format` ma pierwszeństwo |
| `tracking` | px | 0 | dodatkowy odstęp między literami; ujemny zbliża litery i zlewa obrysy |
| `line_height` | mnożnik | 1.15 | wysokość linii względem metryk fontu |
| `condense` | 0.5–1.5 | 1.0 | skalowanie liter w poziomie (zwężenie < 1) |
| `embolden` | px | 0 | pogrubienie kreski przed nałożeniem efektów |
| `jitter` | obiekt lub `null` | `null` | „skaczące” litery, patrz 3.9 |
| `spray` | obiekt | – | faktura sprayu, patrz 3.10 |
| `preview` | lista stringów | 3 linie testowe | teksty do podglądu `*_preview.png` |
| `preview_bg` | HEX lub `"transparent"` | `#ffffff` | tło podglądu (tylko podgląd, atlas jest zawsze przezroczysty) |
| `title` | obiekt | `{ "align": "center", "padding": 8 }` | opcje PNG całego napisu; align: left/center/right, padding: 0–200 pikseli końcowych; `splatter`, patrz 3.11 |
| `auto_diacritics` | bool | `true` | składanie brakujących polskich liter z akcentów zawartych w foncie |

### 3.2 `fill` – wypełnienie (przód litery)

| Parametr | Typ | Domyślnie | Opis |
|---|---|---|---|
| `stops` | lista `[pozycja, HEX]` | **wymagany** | punkty gradientu pionowego; pozycja 0 = góra, 1 = dół |
| `gradient_space` | `"glyph"` / `"line"` | `"glyph"` | `glyph`: gradient rozciągnięty na każdą literę osobno; `line`: wspólny dla całej linii (małe litery dostają dolną część gradientu) |

Wypełnienie jednolite: dwa punkty z tym samym kolorem.

### 3.3 `outline` – obrys

| Parametr | Typ | Domyślnie | Opis |
|---|---|---|---|
| `color` | HEX | **wymagany** | kolor obrysu |
| `width` | px | **wymagany** | grubość; 0 = brak obrysu |

Obrys obejmuje literę razem z bokiem 3D (`side`), dzięki czemu cała bryła ma jeden kontur.

### 3.4 `side` – bok 3D

| Parametr | Typ | Domyślnie | Opis |
|---|---|---|---|
| `depth` | px | – | grubość boku (przesunięcie w dół) |
| `dx` | px | 0 | dodatkowe przesunięcie w prawo (ujemne = w lewo), daje wrażenie perspektywy |
| `color_top` | HEX | – | kolor boku u góry litery |
| `color_bottom` | HEX | – | kolor boku u dołu |
| `enabled` | bool | `true` | |

Typowo bok jest ciemniejszy i cieplejszy niż przód litery (złoto → pomarańcz).

### 3.5 `bevel` – wypukłość

Liczona z mapy odległości od krawędzi litery: brzegi są zaokrąglane i oświetlane z jednego kierunku.

| Parametr | Typ | Domyślnie | Opis |
|---|---|---|---|
| `size` | px | – | szerokość zaokrąglonej krawędzi |
| `soften` | px | 1.0 | wygładzenie mapy wysokości |
| `light_angle` | stopnie | – | kierunek światła: 90 = z góry, 100–120 = z góry-lewej |
| `highlight_color` | HEX | – | kolor oświetlonych krawędzi |
| `highlight_strength` | 0–1 | – | siła rozjaśnienia |
| `shadow_color` | HEX | – | kolor krawędzi w cieniu |
| `shadow_strength` | 0–1 | – | siła przyciemnienia |
| `enabled` | bool | `true` | |

### 3.6 `gloss` – połysk

| Parametr | Typ | Domyślnie | Opis |
|---|---|---|---|
| `color` | HEX | – | zwykle biały |
| `opacity` | 0–1 | – | siła połysku |
| `inset` | px | – | odsunięcie od krawędzi litery |
| `height` | 0–1 | – | jaka część wysokości litery (od góry) jest objęta |
| `blur` | px | – | miękkość przejścia |
| `enabled` | bool | `true` | |

### 3.7 `shadow` – cień i poświata

| Parametr | Typ | Domyślnie | Opis |
|---|---|---|---|
| `color` | HEX | – | kolor cienia |
| `opacity` | 0–1 | – | krycie |
| `dx`, `dy` | px | – | przesunięcie |
| `blur` | px | 0 | rozmycie (0 = twardy, komiksowy cień) |
| `enabled` | bool | `true` | |

**Poświata (glow):** `dx = 0`, `dy = 0`, duży `blur` (10–14), jasny kolor, wysokie krycie (0.7–0.9).

### 3.8 `extrude` – podstawa poza obrysem

Starszy wariant efektu 3D: ciemna bryła pod całym obrysem. W nowych stylach zwykle zastąpiony przez `side`.

| Parametr | Typ | Domyślnie | Opis |
|---|---|---|---|
| `color` | HEX | – | kolor podstawy |
| `depth` | px | – | przesunięcie w dół |
| `opacity` | 0–1 | 1.0 | krycie |
| `blur` | px | 0 | rozmycie |
| `enabled` | bool | `true` | |

### 3.9 `jitter` – skaczące litery

| Parametr | Typ | Domyślnie | Opis |
|---|---|---|---|
| `rotate` | stopnie | 0 | maksymalny obrót litery (losowo ±) |
| `y` | px | 0 | maksymalne przesunięcie w pionie (losowo ±) |
| `seed` | liczba | 0 | ziarno losowania; inny `seed` = inny układ |

Losowanie jest stałe dla danego znaku: „o” zawsze jest obrócone tak samo. W długim tekście
powtarzające się litery mogą to zdradzać, więc do opisów i liczb ustaw `"jitter": null`.

### 3.10 `spray` – faktura sprayu

| Parametr | Typ | Domyślnie | Opis |
|---|---|---|---|
| `grain` | 0–1 | 0.06 | szum jasności na pomalowanej literze |
| `overspray` | 0–1 | 0.4 | gęstość luźnych kropek farby wokół krawędzi |
| `radius` | px | 6 | jak daleko sięgają kropki |
| `color` | hex | kolor krawędzi | kolor kropek |
| `opacity` | 0–1 | 0.85 | krycie kropek |
| `seed` | liczba | 0 | ziarno losowania |

### 3.11 `title.splatter` – rozbryzgi farby

Tylko dla PNG całego napisu (`glyfetti title`). Plamy są rozrzucane wokół tekstu.

| Parametr | Typ | Domyślnie | Opis |
|---|---|---|---|
| `count` | liczba | 12 | plamy za tekstem |
| `front` | liczba | 0 | małe plamy na tekście |
| `size` | `[min, max]` px | `[60, 180]` | zakres promienia plam |
| `colors` | lista hex | 6 jaskrawych kolorów | kolory plam |
| `seed` | liczba | 0 | ziarno losowania |

---

## 4. Słownik: opis słowny → parametry

Używany przez czat (MCP) i jako ściągawka dla ludzi.

| Gdy użytkownik mówi… | Ustaw w `simple`, chyba że zaznaczono inaczej |
|---|---|
| złote, miodowe | paleta `gold` lub `base_color: #F5B845` |
| kremowe, waniliowe | paleta `cream` |
| srebrne, metaliczne | paleta `silver` (gradient z kilkoma pasami jasności) |
| 3D, wypukłe, grube, „jak klocek” | `depth_3d` 0.6–0.9 |
| płaskie, minimalistyczne | `depth_3d: 0`, `shine: 0`, `shadow: "none"` lub `"soft"` |
| z cieniem, miękki cień | `shadow: "soft"` |
| komiksowe, cartoon, „BUM!” | `shadow: "hard"`, `shine: 0`, `outline: "#000000"`, `playful` 0.5 |
| świecące, neon, poświata, magiczne | `glow: <jasny kolor bazy>` |
| cukierkowe, błyszczące, żelkowe | `shine` 0.7–0.9 |
| matowe | `shine` 0–0.2 |
| wąskie, smukłe, condensed | `width` 0.75–0.85 |
| grube, ciężkie, bold | `weight` 2–4 |
| delikatne, cienkie | `weight` 0, `outline_width: "thin"` |
| zabawne, ręczne, bajkowe | `playful` 0.3–0.5, font Grandstander lub Chewy |
| poważne, eleganckie | `playful: 0`, font Baloo 2 lub Dosis |
| ciasno, zlane litery | `spacing` −4 do −8 |
| do przycisku | `outline: "dark"`, `depth_3d` 0.3, białe wypełnienie |
| do drobnego tekstu UI | preset `flat_ui`, `jitter: null`, bez bevela |

### Nazwane palety

| Paleta | Wypełnienie (góra → dół) | Bok 3D | Obrys |
|---|---|---|---|
| `gold` | #FFF1BC → #FCE288 → #F8C95A | #EFA032 → #C46A14 | #562506 |
| `cream` | #FFFDF5 → #FBF0D6 → #F1DDB0 | #C9A36B → #8E6838 | #3E1E0A |
| `candy` | #FFE6F1 → #FF9CC7 → #FF5E9E | #E2457F → #9E1C50 | #5A0F2E |
| `mint` | #FFFFFF → #E6FFD9 | #3F8F2E → #27611B | #1F4D17 |
| `ice` | #FFFFFF → #C8F0FF → #62C2F2 | #2E8FD2 → #174F88 | #0E2F55 |
| `fire` | #FFF8B5 → #FFC93C → #FF5E14 | #D23A10 → #7E1404 | #3A0A02 |
| `magic` | #FAF0FF → #CFA6FF → #8C55F0 | #6234C2 → #38197A | #1E0D40 |
| `wood` | #D39657 → #8B5426 | #5A3215 → #3B1F0B | #3B1F0B |
| `silver` | #FFFFFF → #D5DCE3 → #8C96A1 → #C9D1D9 → #EEF2F5 | #5C6671 → #2F363E | #1B2026 |

---

## 5. Presety

Wszystkie presety mają pełny zestaw znaków: A–Z, a–z, ĄĆĘŁŃÓŚŹŻ ąćęłńóśźż, cyfry,
interpunkcję i symbole (`! ? . , : ; % + - – × * / \ # ' " = ( ) [ ] { } < > & @ _ ~ ^ $ € … « » „ ” “`).

| # | Preset | Font | Charakter | Kluczowe ustawienia | Do czego |
|---|---|---|---|---|---|
| 1 | `honey_gold` | Titan One | złote litery 3D, ciepłe | bok 3D 6 px, bevel, połysk, miękki cień, zwężenie 77%, jitter | tytuły, ekrany zwycięstwa |
| 2 | `cream_sign` | Grandstander Black | kremowy napis, beżowy bok | bok 5 px, delikatny bevel, zwężenie 80% | nagłówki na ciemnym drewnie |
| 3 | `candy_pink` | Sniglet (+PL*) | cukierkowy róż | mocny połysk (0.45), bevel, bok 6 px | bonusy, sklep, nagrody |
| 4 | `mint_button` | Baloo 2 ExtraBold | białe wypełnienie, zielony bok | bok 5 px, bez połysku, zwężenie 85% | napisy na zielonych przyciskach |
| 5 | `ice_blue` | Titan One | lodowy błękit | poświata #9BE3FF, połysk 0.5 | efekty zamrożenia |
| 6 | `fire` | Titan One | ogień, żółć → czerwień | pomarańczowa poświata, mocniejszy jitter | combo, mnożniki punktów |
| 7 | `magic_purple` | Grandstander Black | fioletowa magia | fioletowa poświata, bok 5 px | power-upy, czary |
| 8 | `comic_pop` | Titan One | płaski komiks | żółć bez gradientu, czarny obrys 5 px, twardy cień 6/6, mocny jitter | „BUM!”, wykrzyknienia |
| 9 | `wood_label` | Grandstander ExtraBold | brąz na pergaminie | cienki obrys 3 px, płytki bok 3 px | etykiety, panele, ustawienia |
| 10 | `silver_metal` | Baloo 2 ExtraBold | metaliczne srebro | gradient 5-punktowy, bevel 0.6 | osiągnięcia, rankingi, 2. miejsce |
| 11 | `chocolate_cream` | Chewy (+PL*) | ręczny, kremowy | gruby obrys 6 px, podstawa `extrude`, jitter | casualowe tytuły, słodycze |
| 12 | `flat_ui` | Dosis ExtraBold | prosty tekst interfejsu | ciemny brąz, biała obwódka 2 px, lekki cień, bez efektów 3D | opisy, liczby, drobny tekst |

\* Fonty oznaczone „+PL” nie mają oryginalnie znaków ą ć ę ń ś ź ż. Glyfetti składa je automatycznie
podczas budowania z akcentów zawartych w foncie (`auto_diacritics`, domyślnie włączone) i zapisuje
w `~/.cache/glyfetti`. Zmodyfikowanych fontów nie dołączamy do repozytorium (licencja OFL).

---

## 6. Fonty

| Font | Licencja | Polskie znaki | Osie | Charakter |
|---|---|---|---|---|
| Titan One | OFL | natywnie | – | bardzo ciężki, okrągły, wysokie małe litery |
| Grandstander | OFL | natywnie | `wght` 100–900 | ręczny, bajkowy, nieregularny |
| Baloo 2 | OFL | natywnie | `wght` 400–800 | okrągły, czytelny, szeroki (często zwężany) |
| Dosis | OFL | natywnie | `wght` 200–800 | wąski, zaokrąglone końcówki, do UI |
| Chewy | Apache 2.0 | składane automatycznie | – | ręczny, „gumowy” |
| Sniglet | OFL | składane automatycznie | – | bąbelkowy, bardzo okrągły |
| Lilita One | OFL | częściowo (brak ą ę ż nawet po łataniu) | – | ciężki, kreskówkowy |
| Fredoka | OFL | składane automatycznie | `wght`, `wdth` | miękki, przyjazny |

Każdy inny font TTF/OTF też zadziała. `glyfetti check-font <plik>` pokazuje, których znaków brakuje.

---

## 7. Pliki wynikowe

| Plik | Zawartość |
|---|---|
| `<name>.png` | atlas z przezroczystością |
| `<name>.fnt` | metryki w formacie BMFont (tekstowy, XML lub binarny wg `fnt_format`) – Godot, libGDX, Phaser, Cocos, Defold… |
| `<name>.json` | metryki dla importera Unity (TextMeshPro) |
| `<name>_preview.png` | tekst złożony z atlasu – test metryk i wyglądu |
| `<name>_atlas_on_white.png` | atlas na białym tle do przeglądania |

---

## 8. Znane ograniczenia

- **Bitmapa:** tekst w grze nie powinien być większy niż `size`; na duże tytuły wygeneruj osobny atlas z większym `size`.
- **Kerning obejmuje poziome korekty szerokości par**; kształtowanie kontekstowe, ligatury i inne korekty pozycji wymagają silnika składu.
- **Jitter jest przypisany do znaku**, więc powtarzające się litery wyglądają identycznie.
- **Obrysy liter nachodzą na siebie** przy mocno ujemnym `tracking`; wspólny obrys całego napisu uzyskasz poleceniem `glyfetti title`.
- **Efekty TMP z Inspektora** (Outline, Underlay) nie działają z kolorowym atlasem – efekty są już „wypalone”.
