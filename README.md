# DokladFlow

Interní webový portál pro automatické zpracování CMR, faktur a účtenek. Celý dashboard a firemní data vidí pouze jednatel **Vratislav**. Zaměstnanec může pouze nahrávat vlastní fotografie a zobrazit svůj vlastní výpis za zvolené období.

## Co MVP umí

- hromadně přijmout fotografie JPG/PNG/WebP a PDF,
- rozpoznat CMR nebo daňový doklad přes vyměnitelný AI modul,
- vytěžit číslo CMR, datum, dodavatele, základ DPH, DPH a částku celkem,
- importovat přepravy z Excelu nebo CSV od Konspedu,
- normalizovat číslo CMR a spárovat doklad s přepravou,
- přiřadit řidiče kamionu podle SPZ, řidiče nebo trasy,
- poskytnout Vratislavovi souhrnný dashboard, fronty, kontrolu a účetní export,
- omezit zaměstnance na nahrávání a osobní časově filtrovaný výpis,
- vést audit změn a exportovat schválené náklady do českého CSV,
- spustit se bez cloudových přístupů v deterministickém demonstračním režimu.

> Důležité: lokální režim `mock` neprovádí skutečné OCR. Slouží jen k demonstraci celého toku. Pro reálné dokumenty nastavte Google Document AI.

## Přístupy a role

| Role | Oprávnění |
|---|---|
| Vratislav — jednatel | dashboard, všechny doklady, přepravy, opravy, importy, účetnictví a nastavení |
| Zaměstnanec | nahrání fotografie/PDF a pouze vlastní výpis za zvolené období |

Aktuálně je implementované skutečné přihlášení přes `HttpOnly` session cookie a jednotný PIN login:

- uživatel zadá pouze PIN, systém automaticky určí profil,
- **Jednatel (Vratislav):** PIN s délkou minimálně 6 číslic,
- **Řidič kamionu:** PIN s délkou přesně 4 číslice,
- řidiče přidává jednatel v aplikaci (Nastavení) zadáním jména a PINu,

## Architektura a tok dat

```text
Telefon řidiče ─┐
                 ├─> FastAPI ─> Google Document AI ─> vytěžená data
Excel Konsped ──┘      │                                  │
                       └──────── párování CMR <───────────┘
                                      │
                             pravidla přiřazení
                         ┌────────────┼────────────┐
                       Tonda        Karel        Jarda
                         └────────────┼────────────┘
                               účetní CSV export
```

- **Frontend:** React, JavaScript, Vite, vlastní responzivní CSS
- **Backend:** Python, FastAPI, SQLAlchemy
- **Lokální databáze:** SQLite; přes `DATABASE_URL` lze přepnout na PostgreSQL
- **OCR/AI:** Google Cloud Document AI nebo lokální `mock`
- **Soubory:** lokální adresář `backend/storage` pro vývoj

## Lokální spuštění ve Windows

### 1. Frontend

```powershell
npm install
npm run dev
```

Aplikace standardně použije port `5173`. V aktuálním pracovním prostředí je port obsazený jinou službou, proto DokladFlow běží na `http://127.0.0.1:5174`.

### 2. Backend

Zvolte Python interpreter ve VS Code a nainstalujte balíčky:

```powershell
cd backend
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m uvicorn app.main:app --reload --port 8001
```

API poběží na `http://127.0.0.1:8001`, dokumentace API na `http://127.0.0.1:8001/docs`. Port `8000` je v aktuálním prostředí obsazený jinou aplikací.

Úloha VS Code **DokladFlow: spustit vše** spustí obě části na portech 5174 a 8001. Úloha **DokladFlow: ověřit projekt** provede lint, produkční sestavení a backendové testy.

## Nastavení přihlášení

V `backend/.env` nastavte minimálně:

```dotenv
OWNER_NAME=Vratislav
OWNER_PIN=629911
OWNER_SESSION_DAYS=1
EMPLOYEE_SESSION_DAYS=30
SESSION_COOKIE_NAME=dokladflow_session
SESSION_SECURE=false
SESSION_SIGNING_KEY=dokladflow-dev-signing-key
```

Poznámka:
- v produkci nastavte `SESSION_SECURE=true` (HTTPS),
- PINy jsou jen MVP varianta; dlouhodobě je vhodné SSO/OIDC nebo magic link/OTP.

## Google Cloud Document AI

1. V Google Cloud projektu aktivujte Document AI API.
2. V regionu `eu` vytvořte processor. Pro produkci je vhodný vlastní classifier/extractor s entitami níže; pro faktury lze využít Invoice Parser.
3. Service accountu přidělte minimálně roli pro zpracování dokumentů.
4. Stáhněte JSON klíč mimo repozitář.
5. V `backend/.env` nastavte:

```dotenv
DOCUMENT_AI_PROVIDER=google
GOOGLE_CLOUD_PROJECT=vas-projekt
GOOGLE_CLOUD_LOCATION=eu
GOOGLE_DOCUMENT_AI_PROCESSOR_ID=id-processoru
GOOGLE_APPLICATION_CREDENTIALS=C:\bezpecna\cesta\service-account.json
```

Backend očekává entity:

- CMR: `cmr_number` (případně `cmr` nebo `document_number`),
- daňový doklad: `invoice_date`, `supplier_name`, `net_amount`, `vat_amount`, `vat_rate`, `total_amount`.

Jeden vlastní processor nemusí optimálně pokrýt CMR i faktury. Produkční varianta má obvykle nejprve classifier a poté samostatný CMR extractor a Invoice/Expense processor.

## Import tabulky Konsped

Podporované formáty jsou XLSX, XLS a CSV. Povinný je pouze sloupec `CMR` nebo `Číslo CMR`. Rozpoznané názvy dalších sloupců:

| Hodnota | Podporované názvy |
|---|---|
| datum | Datum, Datum přepravy, Date |
| řidič | Řidič, Jméno řidiče, Driver |
| vozidlo | SPZ, RZ, License plate |
| trasa | Trasa, Route |
| cena | Cena, Cena přepravy, Price |
| měna | Měna, Currency |
| řidič kamionu | Řidič kamionu, Driver |

Opakovaný import aktualizuje existující přepravu podle normalizovaného čísla CMR.

## Hlavní API

| Metoda | Cesta | Účel |
|---|---|---|
| `GET` | `/api/health` | stav backendu a AI provideru |
| `POST` | `/api/auth/login` | přihlášení pouze PINem, profil se určí automaticky |
| `GET` | `/api/auth/session` | načtení aktivní session |
| `POST` | `/api/auth/logout` | odhlášení |
| `GET` | `/api/employees` | seznam řidičů (jen jednatel) |
| `POST` | `/api/employees` | přidání řidiče: jméno + 4místný PIN |
| `GET` | `/api/dashboard` | metriky a vytížení týmu |
| `GET` | `/api/documents` | filtrovaná fronta dokladů |
| `GET` | `/api/me/documents` | vlastní výpis přihlášeného zaměstnance |
| `POST` | `/api/documents/upload` | nahrání a AI zpracování |
| `PATCH` | `/api/documents/{id}` | kontrola a oprava hodnot |
| `POST` | `/api/transports/import` | import Konsped Excel/CSV |
| `GET` | `/api/transports` | seznam přeprav |
| `GET` | `/api/accounting/export.csv` | export schválených nákladů |

## Testy a sestavení

```powershell
npm run lint
npm run build
cd backend
python -m pytest
```

Aktuální automatické testy ověřují normalizaci CMR, seed databáze, API fronty, zákaz vstupu zaměstnance do správy a oddělení osobních výpisů.

## Co rozhodnout před produkcí

1. **Účetní program:** nyní se exportuje univerzální CSV se středníkem a UTF-8 BOM. Po určení programu (např. Pohoda, Money S3, Helios) se doplní jeho přesné schéma nebo API.
2. **Vstup od řidičů:** webový upload je hotový základ; WhatsApp, e-mail nebo mobilní aplikace vyžadují samostatnou integrační bránu.
3. **Přihlášení a role:** aktuální řešení je interní cookie session. Pro produkci doporučeno nahradit SSO/OIDC.
4. **Úložiště:** lokální disk nahradit Cloud Storage a nastavit šifrování, retenční dobu a zálohy.
5. **Zpracování:** OCR přesunout do fronty úloh, přidat retry, monitoring a dead-letter queue.
6. **Databáze:** pro více uživatelů použít PostgreSQL a databázové migrace Alembic.
7. **GDPR a audit:** potvrdit retenční pravidla, přístupová oprávnění a nakládání s osobními údaji.

## Stav MVP

Frontend i backend jsou sestavitelné, API má demonstrační data a aplikace funguje bez externích přístupů. Skutečná kvalita vytěžení závisí na natrénovaném Google Document AI processoru a reprezentativních vzorcích firemních dokladů.
