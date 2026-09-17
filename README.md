# Fantacalcio WhatsApp Bot

Bot che monitora una lega su **Leghe Fantacalcio** (leghe.fantacalcio.it) e
invia una notifica WhatsApp quando viene calcolata una nuova giornata,
oltre a promemoria 24h e 1h prima della chiusura delle formazioni.
Configurabile per più leghe contemporaneamente.

> ⚠️ **Stato del progetto: promemoria formazione verificati e funzionanti;
> notifica "giornata calcolata" temporaneamente disabilitata.** Vedi
> [Leghe Fantacalcio integration](#leghe-fantacalcio-integration): i
> promemoria 24h/1h prima della deadline formazioni sono verificati contro
> chiamate reali all'API e funzionano. La rilevazione "giornata calcolata"
> è invece **disattivata di proposito** (`calculated` sempre `False`) finché
> non è integrato l'endpoint calendario: senza di esso non si può
> distinguere in modo affidabile "la giornata è stata calcolata" da "è solo
> aperto l'inserimento formazioni per quella successiva" (il calcolo è
> un'azione manuale dell'admin, scollegata dall'apertura formazioni — bug
> trovato in review, vedi [Da completare](#da-completare)). Inviare la
> notifica in base alla sola euristica precedente rischiava falsi positivi
> e notifiche mai inviate per giornate calcolate davvero.

---

## Leghe Fantacalcio integration

**Metodo utilizzato:** l'app di Leghe Fantacalcio è una Single Page
Application Angular che si appoggia a una **vera API JSON REST**,
`https://apileague.fantacalcio.it` (non documentata pubblicamente, ma
usata direttamente dal sito stesso — nessuno scraping HTML). Scoperta
osservando due export HAR delle richieste XHR reali del browser
dell'utente durante la navigazione della sua lega.

**Endpoint verificati (risposta 200 con corpo JSON osservato):**
| Endpoint | Uso |
|---|---|
| `GET /onboarding/v1/league/status` | Numero di giornata di Serie A in arrivo (`mday`) e orario di inizio/deadline (`mstr`) |
| `GET /gaming/v1/teamLineup/visualizza/{division}/{competitionId}` | Mappa giornata-lega ↔ giornata-Serie A (`mday`/`cmday`) |
| `GET /onboarding/v1/league/teams?page=1&division={division}` | Elenco squadre della lega, per risalire all'ID squadra dal nome |
| `GET /gaming/v1/teamLineup/{competitionId}/{round}/{serieAMday}/{teamA}/{teamB}` | Dettaglio partita: punteggi (`tot`) e flag esplicito "giornata calcolata" (`cal`) |
| `GET /market/v1/time` | Ora server, per non dipendere dall'orologio del bot |
| `POST /gaming/v1/league/timing` | Millisecondi mancanti alla prossima deadline (ridondante rispetto a `mstr`, usato solo per cross-check) |

**Autenticazione:** ogni richiesta include un header `app_key` (stringa
tipo token, es. `ICiELOObd5DF5uJEATi77CRvHiiRuMU0`) che l'app del sito
invia su tutte le chiamate. Non è stato osservato alcun cookie nelle
richieste catturate (gli export HAR di Chrome/Opera possono comunque
filtrare i cookie per privacy: se in futuro l'`app_key` da solo smettesse
di bastare, andrebbe verificato se serve anche un cookie di sessione
condiviso su `.fantacalcio.it`). Il bot **non automatizza il login**:
l'utente estrae l'`app_key` una volta dal proprio browser già loggato
(vedi [Autenticazione](#autenticazione)).

**Limitazioni:**
- Non è ancora stato possibile osservare una risposta 200 (non da cache
  applicativa, vedi sotto) per `GET /onboarding/v1/league/competition/calendar/{competitionId}`
  (calendario/accoppiamenti) e per `GET /onboarding/v1/league/competition/teams?...&competitionId=...`
  (classifica). Senza il calendario non si conosce l'ID dell'avversario
  in una data giornata, necessario per chiamare l'endpoint di dettaglio
  partita (che espone il flag esplicito `cal` = "giornata calcolata");
  senza la classifica non si ha posizione/punti. Fino a quel momento
  `parse_matchday_status` ritorna sempre `calculated=False`: **il bot non
  invia ancora la notifica "giornata calcolata"** (i promemoria formazione
  restano attivi, non dipendono da questo). Vedi [Da completare](#da-completare).
- L'app usa un proprio meccanismo di cache/ETag (header `if-none-match`
  generati lato client) indipendente dalla cache del browser: anche con
  "Disable cache" attivo in DevTools, richieste già viste nella sessione
  tornano `304` senza corpo. Bisogna forzare una sessione pulita (finestra
  di navigazione in incognito) per catturarne il corpo reale.
- Rispetta i termini d'uso del sito: intervallo di polling non aggressivo
  (default 5 minuti), nessun bypass di misure di sicurezza, nessuna
  automazione del login.
- Il client di Leghe Fantacalcio è isolato dietro l'interfaccia in
  `app/fantacalcio/models.py`: se in futuro cambiassero gli endpoint,
  basta riscrivere `client.py`/`parser.py` senza toccare il resto
  dell'applicazione.

### Da completare

Serve la risposta reale (200, non 304) di questi due endpoint per:
1. **riattivare la notifica "giornata calcolata"** in modo affidabile
   (priorità alta — vedi limitazione sopra): il flag `cal` dell'endpoint
   di dettaglio partita conferma il calcolo reale, ma richiede l'ID
   dell'avversario, che si ottiene dal calendario;
2. popolare punteggio, avversario e classifica nel testo del messaggio.

Endpoint mancanti:
- `GET https://apileague.fantacalcio.it/onboarding/v1/league/competition/calendar/{competitionId}`
- `GET https://apileague.fantacalcio.it/onboarding/v1/league/competition/teams?page=1&pageSize=50&competitionId={competitionId}`

Per catturarle: apri una finestra di navigazione **in incognito/privata**
(cache dell'app pulita), fai login alla lega, apri le pagine
Classifica/Calendario, poi F12 → Network → filtro Fetch/XHR → tasto
destro sulle due richieste sopra → "Copy → Copy response" (o "Save all
as HAR" se preferisci). Una volta ottenuti:
1. completare `parse_calendar`/`parse_standings` in `app/fantacalcio/parser.py`
   e i metodi `get_results`/`get_team_status` in `app/fantacalcio/client.py`
   (attualmente stub con TODO espliciti);
2. in `parse_matchday_status`, sostituire `calculated=False` con una vera
   verifica del flag `cal` per `last_calculated_round` (richiede
   l'ID squadra dell'utente + l'ID avversario di quella giornata dal
   calendario, poi chiamare l'endpoint di dettaglio partita).

In alternativa, da una macchina con accesso di rete reale:
```bash
python scripts/dump_pages.py mantra-cormolittoriano
```
salva in `tests/fixtures/dump/` tutte le risposte JSON note, incluse
(se non cachate) calendario e classifica.

---

## Architettura

```text
apileague.fantacalcio.it (JSON)
       ↓
FantacalcioClient (HTTP + app_key)      app/fantacalcio/client.py
       ↓
parser.py (JSON -> modelli)             app/fantacalcio/parser.py
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
2. Apri gli strumenti sviluppatore (F12) → scheda **Network** → filtro
   **Fetch/XHR** → clicca su una qualsiasi richiesta verso
   `apileague.fantacalcio.it` (es. `league/status`).
3. Nella scheda **Headers** di quella richiesta, cerca l'header di
   richiesta `app_key` e copiane il valore.
4. Incolla il valore nella variabile d'ambiente indicata da
   `api_key_env` per quella lega in `config/leagues.yaml`
   (es. `FANTACALCIO_API_KEY_MANTRA_CORMOLITTORIANO` in `.env`).
5. Prendi nota anche del `competition_id`: apri la Classifica sul sito e
   guarda l'URL, es. `.../view/competition/706778/standings` →
   `competition_id: 706778` da mettere in `config/leagues.yaml`.
6. Se l'`app_key` scade o smette di funzionare (le chiamate iniziano a
   fallire con errore di autenticazione nei log, senza che il valore
   venga mai loggato), ripeti questi passaggi.

### 3. Configurare le leghe

Modifica `config/leagues.yaml` (copiato da `config/leagues.example.yaml`).
Ogni voce è una lega indipendente:

```yaml
leagues:
  - id: mantra-cormolittoriano
    name: "Mantra Cormolittoriano"
    url: "https://leghe.fantacalcio.it/mantra-cormolittoriano/"
    season: "2025-26"
    team_name: "Nome Squadra"          # esattamente come in classifica
    competition_id: 706778             # dall'URL della Classifica sul sito
    division: "A"
    api_key_env: FANTACALCIO_API_KEY_MANTRA_CORMOLITTORIANO
    recipients:
      - "393331234567"
      - "393401234567"
    poll_interval_seconds: 300
    reminder_offsets_hours: [24, 1]
```

Per aggiungere una seconda lega, aggiungi un'altra voce con `id`,
`competition_id`, `api_key_env` (puntando a un'altra variabile
d'ambiente) e `recipients` propri: ogni lega può avere destinatari,
intervallo di polling e squadra da seguire completamente diversi.

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
  `app_key`, access token WhatsApp o numeri di telefono reali.
- Nessun log include il valore dell'`app_key` o dell'access token
  WhatsApp.
- Tutte le richieste HTTP hanno timeout configurato.
- La configurazione viene validata all'avvio (fail-fast con messaggio
  chiaro se manca qualcosa).

---

## Estensioni future (non incluse in questa versione)

Il codice è strutturato per rendere semplice aggiungere in futuro:
comando `classifica`/`risultati`/`mia squadra` via messaggi WhatsApp in
ingresso, notifica di variazione classifica, riepilogo settimanale,
supporto Telegram, pannello web, PostgreSQL al posto di SQLite.
