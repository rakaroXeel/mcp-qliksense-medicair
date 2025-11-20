# Analisi Progetto: Qlik Sense MCP Server

## Panoramica

Server **Model Context Protocol (MCP)** per integrazione con **Qlik Sense Enterprise APIs**. Fornisce un'interfaccia unificata per operazioni su Repository API e Engine API tramite protocollo MCP.

**Versione**: 1.3.4  
**Stato**: Production Ready | 10/10 Tools Working  
**Linguaggio**: Python 3.12+

---

## Architettura

### Componenti Principali

1. **QlikSenseMCPServer** (`server.py`)
   - Gestisce operazioni del protocollo MCP
   - Registrazione tool e routing richieste
   - Autenticazione tramite certificati

2. **QlikRepositoryAPI** (`repository_api.py`)
   - Client HTTP per Repository API
   - Operazioni su metadati applicazioni
   - Porta: 4242 (default)

3. **QlikEngineAPI** (`engine_api.py`)
   - Client WebSocket per Engine API
   - Estrazione dati e analisi
   - Porta: 4747 (default)

4. **QlikSenseConfig** (`config.py`)
   - Gestione configurazione da variabili d'ambiente
   - Validazione certificati e connessioni

---

## Tool Disponibili (10)

### Repository API Tools
- **`get_apps`**: Lista applicazioni con filtri (nome, stream, pubblicazione) e paginazione
- **`get_app_details`**: Dettagli applicazione (metadati, tabelle, campi, master items)

### Engine API Tools
- **`get_app_sheets`**: Lista fogli con titolo e descrizione
- **`get_app_sheet_objects`**: Oggetti di un foglio (ID, tipo, descrizione)
- **`get_app_script`**: Estrazione script di caricamento
- **`get_app_field`**: Valori campo con paginazione e ricerca wildcard
- **`get_app_variables`**: Variabili divise per sorgente (script/UI) con filtri
- **`get_app_field_statistics`**: Statistiche complete campo (min, max, avg, median, std dev)
- **`engine_create_hypercube`**: Creazione hypercube per analisi dati con sorting personalizzato
- **`get_app_object`**: Layout oggetto specifico (GetObject + GetLayout)

---

## Configurazione

### Variabili d'Ambiente Richieste

```bash
QLIK_SERVER_URL=https://your-server.company.com
QLIK_USER_DIRECTORY=COMPANY
QLIK_USER_ID=username
QLIK_CLIENT_CERT_PATH=/path/to/client.pem
QLIK_CLIENT_KEY_PATH=/path/to/client_key.pem
QLIK_CA_CERT_PATH=/path/to/root.pem
```

### Variabili Opzionali

```bash
QLIK_REPOSITORY_PORT=4242      # Default: 4242
QLIK_PROXY_PORT=4243           # Default: 4243
QLIK_ENGINE_PORT=4747          # Default: 4747
QLIK_HTTP_PORT=443             # Per metadata requests
QLIK_VERIFY_SSL=true           # Default: true
QLIK_HTTP_TIMEOUT=10.0         # Secondi
QLIK_WS_TIMEOUT=8.0            # Secondi
QLIK_WS_RETRIES=2              # Tentativi connessione
LOG_LEVEL=INFO                 # DEBUG, INFO, WARNING, ERROR
```

---

## Dipendenze Principali

- `mcp>=1.1.0` - Protocollo MCP
- `httpx>=0.25.0` - Client HTTP per Repository API
- `websocket-client>=1.6.0` - Client WebSocket per Engine API
- `pydantic>=2.0.0` - Validazione configurazione
- `python-dotenv>=1.0.0` - Gestione variabili ambiente
- `requests>=2.31.0` - Richieste HTTP aggiuntive

---

## Funzionalità Chiave

### 1. Autenticazione
- Certificati client (client.pem, client_key.pem)
- CA certificate per verifica SSL
- Ticket-based authentication per Proxy API

### 2. Gestione Connessioni
- Retry automatico su endpoint WebSocket multipli
- Timeout configurabili
- Gestione errori "app already open"

### 3. Analisi Dati
- Hypercube con sorting personalizzato (dimensioni e misure)
- Statistiche campo (min, max, avg, median, mode, std dev)
- Ricerca wildcard su valori campo (`*` e `%`)
- Paginazione su tutti i risultati

### 4. Metadati
- Filtri su applicazioni (nome, stream, pubblicazione)
- Estrazione struttura dati (tabelle, campi, relazioni)
- Master items (misure e dimensioni)
- Variabili (script vs UI)

---

## Struttura Progetto

```
qlik-sense-mcp/
├── qlik_sense_mcp_server/
│   ├── server.py          # Server MCP principale
│   ├── config.py          # Gestione configurazione
│   ├── repository_api.py  # Client Repository API (HTTP)
│   ├── engine_api.py      # Client Engine API (WebSocket)
│   └── utils.py           # Funzioni utility
├── certs/                 # Certificati (git ignored)
├── .env.example          # Template configurazione
├── mcp.json.example      # Template configurazione MCP
└── pyproject.toml        # Dipendenze progetto
```

---

## Installazione e Uso

### Quick Start
```bash
uvx qlik-sense-mcp-server
```

### Da PyPI
```bash
pip install qlik-sense-mcp-server
```

### Sviluppo
```bash
git clone https://github.com/rakaroXeel/mcp-qliksense-medicair
cd mcp-qliksense-medicair
make dev
```

---

## Performance

### Tempi Medi Operazioni
- `get_apps`: ~0.5s
- `get_app_details`: 0.5-2s
- `get_app_sheets`: 0.3-1s
- `get_app_script`: 1-5s
- `get_app_field`: 0.5-2s
- `get_app_variables`: 0.3-1s
- `get_app_field_statistics`: 0.5-2s
- `engine_create_hypercube`: 1-10s

### Ottimizzazioni
- Usa filtri per limitare volume dati
- Limita risultati con `max_rows`
- Repository API più veloce per metadati rispetto a Engine API

---

## Sicurezza

- Certificati esclusi da git
- Variabili ambiente per dati sensibili
- Permessi utente minimi richiesti in Qlik Sense
- Aggiornamento certificati regolare
- Monitoraggio accessi API

---

## Note Tecniche

### WebSocket Endpoints
Il client prova automaticamente più endpoint:
1. `wss://host:4747/app/engineData`
2. `wss://host:4747/app`
3. `ws://host:4747/app/engineData` (fallback)
4. `ws://host:4747/app` (fallback)

### Gestione Errori
- App già aperta: recupero handle esistente
- Connessione fallita: retry su endpoint alternativi
- Timeout configurabili per operazioni lunghe

### Formato Dati
- JSON per tutte le risposte
- Paginazione standardizzata
- Filtri case-insensitive di default
- Supporto wildcard (`*` e `%`)

---

## Limitazioni

- Python 3.12+ richiesto
- Accesso rete a server Qlik Sense (porte 4242, 4243, 4747)
- Certificati validi necessari
- Limiti paginazione: max 50 app, max 100 valori campo

---

## Link Utili

- **Repository**: https://github.com/rakaroXeel/mcp-qliksense-medicair
- **PyPI**: https://pypi.org/project/qlik-sense-mcp-server/
- **Licenza**: MIT

