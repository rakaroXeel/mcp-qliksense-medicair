# Comandi per Avviare il Server

## ⚠️ IMPORTANTE: Usa `py` invece di `python` su Windows

Su Windows, usa il comando `py` invece di `python` per evitare problemi con gli alias.

## Metodo 1: Con file .env (Consigliato)

### 1. Configura il file .env

Apri il file `.env` nella root del progetto e aggiungi:

```bash
QLIK_SERVER_URL=https://your-qlik-server.company.com
QLIK_API_KEY=your-api-key-here
```

### 2. Avvia il server

```powershell
py -m qlik_sense_mcp_server.server
```

## Metodo 2: Con variabili PowerShell

```powershell
# Imposta le variabili
$env:QLIK_SERVER_URL="https://your-server.com"
$env:QLIK_API_KEY="your-api-key"

# Avvia il server
py -m qlik_sense_mcp_server.server
```

## Metodo 3: Comando unico (tutto in una riga)

```powershell
$env:QLIK_SERVER_URL="https://your-server.com"; $env:QLIK_API_KEY="your-api-key"; py -m qlik_sense_mcp_server.server
```

## Metodo 4: Usando uvx (se installato)

```powershell
uvx --with-env QLIK_SERVER_URL=https://your-server.com --with-env QLIK_API_KEY=your-api-key qlik-sense-mcp-server
```

## Verifica Configurazione

### Test rapido della configurazione:

```powershell
py -c "from qlik_sense_mcp_server.config import QlikSenseConfig; import os; os.environ['QLIK_SERVER_URL']='test'; os.environ['QLIK_API_KEY']='test'; config = QlikSenseConfig.from_env(); print('Config OK:', config.server_url)"
```

## Troubleshooting

### Errore: "Python non è stato trovato"
✅ **Soluzione**: Usa `py` invece di `python`

### Errore: "Qlik Sense configuration missing"
✅ **Soluzione**: Verifica che `.env` contenga `QLIK_SERVER_URL` e `QLIK_API_KEY`

### Errore: "ModuleNotFoundError"
✅ **Soluzione**: Esegui `py -m pip install -e .` per installare il progetto

## Esempio Completo

```powershell
# 1. Vai nella directory del progetto
cd C:\Projects\mcp-qliksense-medicair

# 2. Configura le variabili (o modifica .env)
$env:QLIK_SERVER_URL="https://qlik.company.com"
$env:QLIK_API_KEY="abc123def456ghi789"

# 3. Avvia il server
py -m qlik_sense_mcp_server.server
```

Il server si avvierà e resterà in ascolto per comunicare con i client MCP tramite stdin/stdout.

