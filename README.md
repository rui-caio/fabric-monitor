# NiW Fabric Monitor

Ferramenta de monitorização para **Microsoft Power BI Fabric** — permite acompanhar em tempo real o consumo de capacidade, actividade de utilizadores e métricas de refresh de datasets, através de um dashboard web local.

---

## Funcionalidades

| Tab | O que monitoriza |
|-----|-----------------|
| **Utilização de Capacidade** | Consumo de CU (Compute Units) ao longo do tempo, throttling, breakdown Interactive vs Background, drill-down por timepoint |
| **Log de Actividade** | Eventos de utilizadores (visualizações, refreshes, ligações externas), filtros multi-selecção, rankings, tabela detalhada |
| **Refreshes** | Schedules de datasets, duração média, carga diária estimada, falhas, rankings |

---

## Requisitos

### Sistema

| Requisito | Versão mínima |
|-----------|--------------|
| Python | 3.8+ |
| pip | qualquer versão recente |

### Biblioteca Python

```bash
pip install msal
```

> Todas as outras dependências (`json`, `urllib`, `http.server`, `threading`) fazem parte da biblioteca padrão do Python — sem instalações adicionais.

### Browser

Qualquer browser moderno com suporte a ES6+ (Chrome, Edge, Firefox, Safari).  
O Chart.js é carregado automaticamente via CDN — é necessária ligação à internet na primeira utilização.

---

## Pré-requisitos Microsoft / Azure

Para utilizar esta ferramenta precisas de acesso a:

### 1. Azure Active Directory (Entra ID)

- Uma conta com permissões de **Power BI Admin** ou **Fabric Admin** no tenant
- O **Tenant ID** do teu Azure AD

> Como encontrar: [portal.azure.com](https://portal.azure.com) → Azure Active Directory → Overview → **Directory (tenant) ID**

### 2. Microsoft Fabric Capacity

- Uma capacidade Fabric activa (F-SKU ou P-SKU)
- O **Capacity ID** da capacidade a monitorizar

> Como encontrar: [app.powerbi.com](https://app.powerbi.com) → Admin Portal → Capacity Settings → selecciona a capacidade → o ID aparece no URL ou nas definições

### 3. Dataset de Métricas do Fabric (Microsoft Fabric Capacity Metrics)

A ferramenta lê os dados de capacidade através da app oficial **Microsoft Fabric Capacity Metrics**, que tem de estar instalada no teu tenant.

Precisas de dois IDs desse dataset:

| Variável | O que é |
|----------|---------|
| `METRICS_WS` | ID do Workspace onde a app Capacity Metrics está instalada |
| `METRICS_DS` | ID do Dataset da app Capacity Metrics |

> Como encontrar: abre o workspace da app Capacity Metrics no Power BI → clica no dataset → o URL tem o formato:  
> `app.powerbi.com/groups/{METRICS_WS}/datasets/{METRICS_DS}`

### 4. Permissões necessárias

A conta utilizada na autenticação precisa de:

- `Tenant.Read.All` ou `Tenant.ReadWrite.All` — para o Activity Log
- Acesso de **Viewer** (ou superior) ao workspace da app Capacity Metrics
- **Fabric Administrator** ou **Power BI Administrator** no tenant — para aceder à API de capacidade e refreshables

---

## Instalação

### 1. Clonar o repositório

```bash
git clone https://github.com/rui-caio/fabric-monitor.git
cd fabric-monitor
```

### 2. Instalar dependências

```bash
pip install msal
```

### 3. Configurar o ficheiro `.env`

Copia o ficheiro de exemplo e preenche com os teus valores:

```bash
cp .env.example .env
```

Abre o `.env` e preenche:

```env
TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
CAPACITY_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
METRICS_WS=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
METRICS_DS=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
PORT=8765
```

> **Importante:** O ficheiro `.env` está no `.gitignore` e nunca deve ser partilhado ou commited. Contém informação sensível de configuração.

---

## Utilização

### Arrancar o servidor

```bash
python fabric_proxy.py
```

### Autenticação (primeiro arranque)

Na primeira execução, o terminal mostra um código de autenticação:

```
────────────────────────────────────────────────────────────
  AUTENTICAÇÃO NECESSÁRIA
────────────────────────────────────────────────────────────

  1. Abre: https://microsoft.com/devicelogin
  2. Código: XXXX-XXXX

  À espera...
```

1. Abre o browser em `https://microsoft.com/devicelogin`
2. Introduz o código apresentado no terminal
3. Autentica com a tua conta Microsoft com as permissões necessárias
4. Regressa ao terminal — a autenticação é concluída automaticamente

O token é guardado em memória durante a sessão. Na próxima execução, se o token ainda for válido, a autenticação é feita silenciosamente.

### Abrir o dashboard

Depois de autenticado, abre o browser em:

```
http://localhost:8765
```

### Parar o servidor

```
Ctrl+C
```

---

## Estrutura do projecto

```
fabric-monitor/
├── fabric_proxy.py        # Entry point — inicia o servidor
├── config.py              # Carrega .env e expõe constantes de configuração
├── auth.py                # Autenticação MSAL (Device Code Flow)
├── server.py              # Handler HTTP e função main()
│
├── api/
│   ├── activity.py        # Endpoint /api/activity — eventos de actividade
│   ├── capacity.py        # Endpoint /api/capacity — consumo de CU
│   ├── timepoint.py       # Endpoint /api/timepoint — drill-down de timepoint
│   └── refreshes.py       # Endpoint /api/refreshes — métricas de refresh
│
├── static/
│   └── index.html         # Frontend (HTML + CSS + JavaScript + Chart.js)
│
├── .env                   # Configuração local (NÃO commitar)
├── .env.example           # Template de configuração
└── .gitignore
```

---

## Endpoints da API local

O servidor expõe os seguintes endpoints em `http://localhost:8765`:

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/` | Serve o frontend HTML |
| `POST` | `/api/ping` | Health check |
| `POST` | `/api/auth_status` | Estado da autenticação atual |
| `POST` | `/api/activity` | Eventos de actividade (por intervalo de datas) |
| `POST` | `/api/capacity` | Consumo de CU (por número de horas) |
| `POST` | `/api/timepoint` | Detalhe de operações num timepoint específico |
| `POST` | `/api/refreshes` | Métricas de refresh de datasets |

---

## APIs Microsoft utilizadas

| API | Utilização |
|-----|-----------|
| [Power BI Activity Events API](https://learn.microsoft.com/en-us/rest/api/power-bi/admin/get-activity-events) | Log de actividade de utilizadores |
| [Power BI Capacity Refreshables API](https://learn.microsoft.com/en-us/rest/api/power-bi/admin/get-capacities-refreshables) | Métricas de refresh de datasets |
| [Power BI Execute Queries API](https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/execute-queries-in-group) | Consultas DAX ao dataset Capacity Metrics |

A autenticação é feita via [MSAL Device Code Flow](https://learn.microsoft.com/en-us/azure/active-directory/develop/msal-authentication-flows#device-code) — não são armazenadas passwords ou segredos.

---

## Variáveis de ambiente

| Variável | Obrigatória | Descrição |
|----------|-------------|-----------|
| `TENANT_ID` | Sim | ID do tenant Azure AD |
| `CAPACITY_ID` | Sim | ID da capacidade Fabric a monitorizar |
| `METRICS_WS` | Sim | ID do workspace da app Capacity Metrics |
| `METRICS_DS` | Sim | ID do dataset da app Capacity Metrics |
| `PORT` | Não (default: `8765`) | Porta do servidor local |

---

## Resolução de problemas

### `ERRO: variáveis não configuradas`
O ficheiro `.env` não existe ou está incompleto. Verifica se copiaste o `.env.example` e preencheste todos os valores.

### `ERRO: biblioteca 'msal' não encontrada`
```bash
pip install msal
```

### A autenticação falha ou expira
O token MSAL é guardado apenas em memória. Ao reiniciar o servidor, será pedida nova autenticação. Se a conta não tiver permissões suficientes, o fluxo de device code conclui mas as chamadas à API retornam 403.

### `Activity API erro 403`
A conta autenticada não tem permissões de **Power BI Administrator** ou **Fabric Administrator**. Contacta o administrador do tenant.

### `Capacity API erro 404` ou dados vazios
Confirma que o `METRICS_WS` e `METRICS_DS` correspondem ao workspace e dataset correcto da app **Microsoft Fabric Capacity Metrics**.

### O browser mostra "Proxy não detectado"
O servidor Python não está a correr ou está a usar uma porta diferente. Confirma que `python fabric_proxy.py` está activo no terminal e que o `PORT` no `.env` corresponde ao URL que estás a aceder.

---

## Dependências

| Dependência | Versão | Origem |
|-------------|--------|--------|
| `msal` | qualquer | `pip install msal` |
| `Chart.js` | 4.4.1 | CDN (carregado automaticamente) |
| `JetBrains Mono` | — | Google Fonts (carregado automaticamente) |
| `Syne` | — | Google Fonts (carregado automaticamente) |

---

## Segurança

- As credenciais de configuração (`TENANT_ID`, `CAPACITY_ID`, etc.) são lidas de variáveis de ambiente / ficheiro `.env` e nunca ficam no código
- O ficheiro `.env` está excluído do git via `.gitignore`
- A autenticação Microsoft usa **Device Code Flow** — sem passwords armazenadas
- O servidor HTTP escuta apenas em `127.0.0.1` (localhost) — não é acessível a partir da rede local
