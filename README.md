# Fantacalcio WhatsApp Bot

Bot che monitora una lega su **Leghe Fantacalcio** (leghe.fantacalcio.it) e
invia una notifica WhatsApp quando viene calcolata una nuova giornata,
oltre a promemoria 24h e 1h prima della chiusura delle formazioni.
Configurabile per più leghe contemporaneamente.

> ⚠️ **Stato del progetto: da validare con dati reali.** Vedi la sezione
> [Leghe Fantacalcio integration](#leghe-fantacalcio-integration) qui
> sotto: l'ambiente di sviluppo usato per costruire questo bot non aveva
> accesso di rete a leghe.fantacalcio.it, quindi il parser HTML è stato
> scritto sulla base di pattern plausibili ma **non verificati** contro
> l'HTML reale della lega. Prima di fidarsi delle notifiche in
> produzione, segui i passaggi in [Validazione con la lega reale](#validazione-con-la-lega-reale).

---

## Leghe Fantacalcio integration

**Metodo utilizzato:** HTML scraping autenticato (nessuna API pubblica o
ufficiale nota per Leghe Fantacalcio). Il client (`app/fantacalcio/client.py`)
effettua richieste HTTP GET alle pagine della lega e ne effettua il parsing
(`app/fantacalcio/parser.py`) con BeautifulSoup, privilegiando attributi
`data-*` strutturati quando presenti e ricorrendo al testo visualizzato
solo come fallback.

**Endpoint/dati utilizzati:** pagine `classifica` e `risultati` sotto
l'URL della lega (es. `https://leghe.fantacalcio.it/<slug-lega>/classifica`).
Questi percorsi sono un'**ipotesi**, non confermata: non è stato possibile
osservare le richieste XHR/fetch reali del sito né la struttura HTML
effettiva perché in questo ambiente di sviluppo l'accesso di rete a
`leghe.fantacalcio.it` è bloccato dal proxy, e in ogni caso la lega
richiede un login a cui questo ambiente non ha credenziali.

**Autenticazione:** Leghe Fantacalcio richiede un login. Il bot **non
automatizza il login** (nessun invio di username/password, nessun bypass
di CAPTCHA): riusa invece un cookie di sessione che l'utente ottiene
autenticandosi normalmente, una volta, nel proprio browser. Questo è il
metodo meno fragile e meno invasivo compatibile con l'assenza di
un'API ufficiale. Vedi [Autenticazione](#autenticazione).

**Limitazioni:**
- I selettori CSS in `app/fantacalcio/parser.py` sono marcati esplicitamente
  come non verificati e vanno corretti con l'HTML reale (vedi sotto).
- Il cookie di sessione scade periodicamente; quando accade, il bot logga
  un errore di autenticazione (senza esporre il valore del cookie) e
  continua a ritentare ai cicli successivi finché non viene aggiornato.
- Rispetta i termini d'uso del sito: intervallo di polling non aggressivo
  (default 5 minuti), User-Agent identificabile, nessun bypass di misure
  di sicurezza.
- Il client di Leghe Fantacalcio è isolato dietro l'interfaccia in
  `app/fantacalcio/models.py`: se in futuro emergesse un'API ufficiale o
  endpoint diversi, basta riscrivere `client.py`/`parser.py` senza
  toccare il resto dell'applicazione.

### Validazione con la lega reale

1. Autenticati nella tua lega da browser e ottieni il cookie di sessione
   (vedi [Autenticazione](#autenticazione)).
2. Configura `.env` e `config/leagues.yaml` come descritto sotto.
3. Da una macchina **con accesso di rete reale** al sito (il tuo PC, un
   VPS, un Raspberry Pi — non l'ambiente usato per generare questo
   codice), esegui:
   ```bash
   python scripts/dump_pages.py mantra-cormolittoriano
   ```
   Questo salva l'HTML reale delle pagine `classifica`/`risultati` in
   `tests/fixtures/dump/`.
4. Confronta l'HTML ottenuto con i selettori in cima a
   `app/fantacalcio/parser.py` (sezione "SELETTORI NON VERIFICATI") e
   correggili di conseguenza (nomi di classi CSS, attributi `data-*`,
   percorsi delle pagine in `client.py`).
5. Rilancia `pytest tests/test_parser.py` (idealmente aggiungendo le
   fixture reali) finché il parsing non produce i dati corretti.
6. Testa un ciclo completo con `DRY_RUN=true` (vedi sotto) per vedere il
   messaggio che verrebbe inviato, prima di disattivare il dry-run.

---

## Architettura

```text
Leghe Fantacalcio (HTML)
       ↓
FantacalcioClient (HTTP + cookie)       app/fantacalcio/client.py
       ↓
parser.py (HTML -> modelli)             app/fantacalcio/parser.py
       ↓
modelli normalizzati                    app/fantacalcio/models.py
       ↓
MatchdayChecker / DeadlineReminderChecker   app/monitoring/
       ↓
formatter.py (testo del messaggio)      app/notifications/formatter.py
       ↓
WhatsAppClient (Cloud API)              app/whatsapp/client.py
       ↓
WhatsApp Business Cloud API (Meta)
```

Stato persistente in SQLite (`app/storage/state.py`): tabella
`notifications` (idempotenza giornata calcolata) e `reminders`
(idempotenza promemoria formazione), popolate **solo dopo** un invio
WhatsApp riuscito.

`app/main.py` avvia uno scheduler (APScheduler) con un job per lega
(intervallo configurabile per lega) più un piccolo server HTTP di
health check su `/health`.

---

## Setup rapido

```bash
git clone <repo>
cd Fantabot
cp .env.example .env
cp config/leagues.example.yaml config/leagues.yaml
# compila .env e config/leagues.yaml (vedi sotto)
docker compose up -d
```

### 1. Credenziali WhatsApp (Cloud API)

Il bot usa la **WhatsApp Business Platform / Cloud API** ufficiale di
Meta (non WhatsApp Web/Selenium).

1. Crea un'app su [Meta for Developers](https://developers.facebook.com/)
   e aggiungi il prodotto "WhatsApp".
2. Nella dashboard WhatsApp trovi `Phone number ID` (→
   `WHATSAPP_PHONE_NUMBER_ID`) e un token di accesso temporaneo per i
   test (→ `WHATSAPP_ACCESS_TOKEN`); per l'uso continuativo genera un
   token permanente da un System User in Meta Business Suite.
3. Imposta `WHATSAPP_API_VERSION` (es. `v21.0`; verifica la versione
   corrente supportata nella dashboard Meta).
4. **Finestra di conversazione (24h):** un messaggio di testo libero può
   essere inviato solo se il destinatario ha scritto al numero del bot
   nelle ultime 24 ore. Per notifiche **proattive** (come "giornata
   calcolata", che parte da un evento del bot, non da un messaggio
   dell'utente) è quasi certamente necessario un **Message Template**
   pre-approvato da Meta. Il client (`app/whatsapp/client.py`) supporta
   sia messaggi di testo (`send_text_to_all`) sia template
   (`send_template_to_all`): se i messaggi di testo iniziano a fallire
   fuori dalla finestra di 24h, crea un template in Meta Business Suite
   e passa a `send_template_to_all` in `app/monitoring/checker.py` e
   `reminders.py`.
5. Ogni destinatario deve avere WhatsApp attivo sul numero indicato e —
   nella fase Sviluppo dell'app Meta — deve essere aggiunto come
   destinatario di test nella dashboard, finché l'app non è verificata
   per l'uso in produzione.

### 2. Autenticazione a Leghe Fantacalcio

1. Apri la tua lega nel browser e fai login normalmente
   (es. `https://leghe.fantacalcio.it/mantra-cormolittoriano/`).
2. Apri gli strumenti sviluppatore del browser (F12) →
   scheda **Application/Storage → Cookie** (Chrome/Edge) o
   **Storage → Cookie** (Firefox), seleziona il dominio
   `leghe.fantacalcio.it`.
3. Copia il valore del cookie di sessione (tipicamente `PHPSESSID` o
   simile) — puoi copiare anche l'intera stringa `Cookie` dalla scheda
   Network di una richiesta se preferisci (formato
   `NOME1=valore1; NOME2=valore2`, supportato dal bot).
4. Incolla il valore nella variabile d'ambiente indicata da
   `session_cookie_env` per quella lega in `config/leagues.yaml`
   (es. `FANTACALCIO_SESSION_COOKIE_MANTRA_CORMOLITTORIANO` in `.env`).
5. Il cookie scade periodicamente (logout, cambio password, timeout di
   sessione): quando le richieste iniziano a fallire con errori di
   autenticazione nei log, ripeti questi passaggi.

### 3. Configurare le leghe

Modifica `config/leagues.yaml` (copiato da `config/leagues.example.yaml`).
Ogni voce è una lega indipendente:

```yaml
leagues:
  - id: mantra-cormolittoriano
    name: "Mantra Cormolittoriano"
    url: "https://leghe.fantacalcio.it/mantra-cormolittoriano/"
    season: "2024-25"
    team_name: "Nome Squadra"          # esattamente come in classifica
    session_cookie_env: FANTACALCIO_SESSION_COOKIE_MANTRA_CORMOLITTORIANO
    recipients:
      - "393331234567"
      - "393401234567"
    poll_interval_seconds: 300
    reminder_offsets_hours: [24, 1]
```

Per aggiungere una seconda lega, aggiungi un'altra voce con `id`, `url`,
`session_cookie_env` (puntando a un'altra variabile d'ambiente) e
`recipients` propri: ogni lega può avere destinatari, intervallo di
polling e squadra da seguire completamente diversi.

### 4. Avvio

```bash
docker compose up -d
docker compose logs -f
```

### 5. Verificare i log

```bash
docker compose logs -f fantacalcio-bot
```

Log attesi:
```
INFO  Bot avviato (1 leghe configurate, dry_run=False)
INFO  Controllo lega mantra-cormolittoriano...
INFO  Lega mantra-cormolittoriano: giornata 4 non ancora calcolata.
```

### 6. Testare una notifica manualmente

Senza attendere un calcolo giornata reale:

```bash
# dentro il container, o in locale con l'ambiente virtuale attivo
python -m app.main --test-notification                     # tutte le leghe
python -m app.main --test-notification mantra-cormolittoriano
```

Per verificare il testo dei messaggi **senza inviare nulla** su
WhatsApp, imposta `DRY_RUN=true` in `.env`: i messaggi vengono solo
loggati.

### 7. Health check

```bash
curl http://localhost:8080/health
```

```json
{
  "status": "ok",
  "leagues": [
    {
      "league_id": "mantra-cormolittoriano",
      "last_check_at": "2024-10-01T20:16:00+00:00",
      "last_error": null,
      "last_calculated_matchday": 4
    }
  ]
}
```

### 8. Fermare / riavviare

```bash
docker compose down       # ferma (i dati restano nel volume ./data)
docker compose up -d      # riavvia, recupera lo stato da SQLite
docker compose restart fantacalcio-bot
```

---

## Sviluppo locale (senza Docker)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
cp config/leagues.example.yaml config/leagues.yaml
# compila .env e config/leagues.yaml
python -m app.main
```

### Test

```bash
pytest tests/ -v
```

Copertura attuale: parsing (giornata calcolata/non calcolata, risultati,
stato squadra), idempotenza delle notifiche, nuova giornata → invio,
errore WhatsApp → giornata non marcata come notificata, ripristino dello
stato dopo un riavvio simulato, client WhatsApp (successo, retry su
errori 5xx, nessun retry su errori non recuperabili come 401, dry-run).

---

## Idempotenza e gestione errori

- Una giornata viene marcata come notificata **solo dopo** un invio
  WhatsApp riuscito verso **tutti** i destinatari configurati. Se
  l'invio fallisce, nessuna riga viene scritta e si ritenta al ciclo di
  polling successivo (nessuna notifica persa, nessun duplicato).
- Caso limite documentato: se l'invio riesce ma il salvataggio su SQLite
  fallisce (es. disco pieno nello stesso istante), al ciclo successivo la
  notifica verrebbe ritentata e potenzialmente duplicata. Non è stata
  aggiunta ulteriore complessità per questo scenario estremamente raro;
  se necessario in futuro si può introdurre un ID di operazione
  idempotente lato WhatsApp o una transazione a due fasi.
- Errori di rete/HTTP/parsing non generano mai una notifica WhatsApp:
  vengono solo loggati e registrati nell'health check (`last_error`).
- Retry con backoff sia sulle richieste verso Leghe Fantacalcio (via
  `urllib3.Retry`) sia verso l'API WhatsApp (retry manuale su 429/5xx,
  nessun retry su errori come 401/400).
- Arresto pulito su `SIGTERM`/`SIGINT` (importante per `docker compose down`).

---

## Sicurezza

- `.env` e `config/leagues.yaml` sono in `.gitignore`: non committare mai
  cookie, token o numeri di telefono reali.
- Nessun log include il valore del cookie di sessione o dell'access
  token WhatsApp.
- Tutte le richieste HTTP hanno timeout configurato.
- La configurazione viene validata all'avvio (fail-fast con messaggio
  chiaro se manca qualcosa).
- User-Agent identificabile nelle richieste verso Leghe Fantacalcio.

---

## Estensioni future (non incluse in questa versione)

Il codice è strutturato per rendere semplice aggiungere in futuro:
comando `classifica`/`risultati`/`mia squadra` via messaggi WhatsApp in
ingresso, notifica di variazione classifica, riepilogo settimanale,
supporto Telegram, pannello web, PostgreSQL al posto di SQLite.
