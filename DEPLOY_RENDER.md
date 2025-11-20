# Deploy su Render

## Panoramica

Il server MCP originale comunica tramite stdin/stdout, ma Render richiede un web service HTTP. Ho creato un wrapper HTTP (`http_server.py`) che espone gli stessi tool come endpoint REST.

## Prerequisiti

1. Account Render (https://render.com)
2. Repository Git con il codice
3. Variabili d'ambiente configurate

## Passi per il Deploy

### 1. Aggiungi FastAPI e Uvicorn alle dipendenze

Le dipendenze sono già state aggiunte a `pyproject.toml`:
- `fastapi>=0.100.0`
- `uvicorn>=0.23.0`

### 2. Configurazione Render

#### Opzione A: Usando render.yaml (Consigliato)

Il file `render.yaml` è già stato creato. Render lo rileverà automaticamente.

#### Opzione B: Configurazione Manuale

1. Vai su https://dashboard.render.com
2. Clicca "New +" → "Web Service"
3. Connetti il tuo repository Git
4. Configura:
   - **Name**: `qlik-sense-mcp-server`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -e .`
   - **Start Command**: `python -m qlik_sense_mcp_server.http_server`
   - **Plan**: Starter (o superiore)

### 3. Configura Variabili d'Ambiente

Nella dashboard Render, vai su "Environment" e aggiungi:

**Obbligatorie:**
```
QLIK_SERVER_URL=https://your-qlik-server.com
QLIK_API_KEY=your-api-key-here
```

**Opzionali:**
```
QLIK_REPOSITORY_PORT=4242
QLIK_ENGINE_PORT=4747
QLIK_PROXY_PORT=4243
QLIK_VERIFY_SSL=true
LOG_LEVEL=INFO
PORT=8000
```

**⚠️ IMPORTANTE**: Non committare mai l'API key nel codice! Usa sempre le variabili d'ambiente di Render.

### 4. Deploy

1. Push del codice su Git
2. Render rileverà automaticamente il push
3. Il deploy inizierà automaticamente
4. Monitora i log per eventuali errori

## Endpoint Disponibili

### Health Check
```
GET /health
```
Verifica lo stato del server e la configurazione.

### Lista Tool
```
GET /tools
```
Lista tutti i tool disponibili.

### Esegui Tool
```
POST /tools/execute
Body: {
  "tool_name": "get_apps",
  "arguments": {
    "limit": 10
  }
}
```

### Endpoint Convenienza

#### Lista Applicazioni
```
GET /apps?limit=25&offset=0&name=filter&published=true
```

#### Dettagli Applicazione
```
GET /apps/{app_id}/details
```

#### Script Applicazione
```
GET /apps/{app_id}/script
```

## Test Locale Prima del Deploy

### 1. Installa dipendenze aggiuntive
```powershell
py -m pip install fastapi uvicorn
```

### 2. Avvia il server HTTP localmente
```powershell
$env:QLIK_SERVER_URL="https://your-server.com"
$env:QLIK_API_KEY="your-api-key"
$env:PORT="8000"
py -m qlik_sense_mcp_server.http_server
```

### 3. Testa gli endpoint
```powershell
# Health check
curl http://localhost:8000/health

# Lista tool
curl http://localhost:8000/tools

# Esegui tool
curl -X POST http://localhost:8000/tools/execute `
  -H "Content-Type: application/json" `
  -d '{"tool_name": "get_apps", "arguments": {"limit": 5}}'
```

## Documentazione API

Una volta deployato, la documentazione interattiva sarà disponibile su:
- **Swagger UI**: `https://your-app.onrender.com/docs`
- **ReDoc**: `https://your-app.onrender.com/redoc`

## Troubleshooting

### Errore: "ModuleNotFoundError: No module named 'fastapi'"
✅ **Soluzione**: Verifica che `pyproject.toml` includa fastapi e uvicorn nelle dipendenze

### Errore: "MCP Server configuration invalid"
✅ **Soluzione**: Verifica che `QLIK_SERVER_URL` e `QLIK_API_KEY` siano configurate nelle variabili d'ambiente di Render

### Errore: "Port already in use"
✅ **Soluzione**: Render imposta automaticamente la variabile `PORT`. Non sovrascriverla.

### Errore: "Connection timeout"
✅ **Soluzione**: Verifica che il server Qlik Sense sia accessibile da internet (non solo da rete locale)

## Limitazioni

1. **WebSocket**: Il server HTTP non supporta WebSocket per Engine API in tempo reale
2. **Connessioni Persistenti**: Ogni richiesta HTTP apre una nuova connessione
3. **Timeout**: Le richieste lunghe potrebbero timeoutare (configura timeout appropriati)

## Costi

- **Starter Plan**: Gratuito (con limitazioni)
- **Standard Plan**: $7/mese
- **Pro Plan**: $25/mese

## Sicurezza

1. ✅ Usa HTTPS (Render lo fornisce automaticamente)
2. ✅ Non committare API key nel codice
3. ✅ Configura CORS appropriatamente in produzione
4. ✅ Considera autenticazione aggiuntiva per gli endpoint

## Monitoraggio

Render fornisce:
- Log in tempo reale
- Metriche CPU/Memory
- Alert per errori

## Prossimi Passi

1. Testa localmente con `http_server.py`
2. Configura variabili d'ambiente su Render
3. Fai push del codice
4. Verifica il deploy
5. Testa gli endpoint pubblici

