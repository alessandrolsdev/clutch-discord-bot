# 🤖 Clutch Discord Bot V3.0

<div align="center">

Bot Discord avançado com **Inteligência Artificial**, **Sistema de Áudio em Tempo Real**, **Gamificação** e **Dashboard Web**.

[![CI](https://github.com/alessandrolsdev/clutch-discord-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/alessandrolsdev/clutch-discord-bot/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Discord.py](https://img.shields.io/badge/discord.py-2.3+-blue.svg)](https://github.com/Rapptz/discord.py)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

</div>

---

## 📋 Índice

- [Funcionalidades](#-funcionalidades)
- [Arquitetura](#-arquitetura)
- [Pré-requisitos](#-pré-requisitos)
- [Instalação](#-instalação)
- [Configuração](#%EF%B8%8F-configuração)
- [Uso](#-uso)
- [Comandos Principais](#-comandos-principais)
- [Dashboard Web](#-dashboard-web)
- [Estrutura do Projeto](#-estrutura-do-projeto)
- [Troubleshooting](#-troubleshooting)
- [Contribuindo](#-contribuindo)

---

## ✨ Funcionalidades

### 🎵 Sistema de Áudio Avançado
- **Player com Fila**: `/play` enfileira, com skip, loop, shuffle, mover e volume
- **Streaming direto**: o áudio vai do YouTube ao FFmpeg sem passar pelo disco
- **Playlists**: um link de playlist enfileira até 50 faixas de uma vez
- **Auto-disconnect**: sai da call sozinho quando fica vazia ou ociosa
- **Text-to-Speech (TTS)**: Vozes em português brasileiro natural via Edge TTS
- **Soundboard**: Efeitos sonoros customizáveis com autocomplete
- **Modulador de Voz**: Transforma voz em tempo real usando Pedalboard
- **Sistema de Rádio**: Transmissão bidirecional de áudio via UDP

### 🤖 Inteligência Artificial
- **Chat Inteligente**: Conversa contextual com memória usando Google Gemini 2.5 Flash
- **Personalidades**: Múltiplas personas (Coach, Hacker, Fofoqueira)
- **RPG Generator**: Cria fichas de personagens únicas e engraçadas
- **Análise de Vibe**: Julga membros da call com IA e fala em áudio
- **Compatibilidade**: Testa "shipp" entre membros

### 🏆 Sistema de Gamificação
- **Sistema de XP e Níveis**: Ganha experiência por mensagens e tempo de voz
- **Conquistas (Badges)**: Medalhas desbloqueáveis por marcos
- **Streak System**: Rastreia dias consecutivos de atividade
- **Perfil Customizável**: Bio personalizada e cards visuais
- **Leaderboard**: Ranking automático de membros

### 🛡️ Moderação
- **Automod**: anti-spam, anti-flood, convites, links, menções em massa,
  CAPS e palavras proibidas — com punição escalonada
- **Punições**: ban, kick, castigo (timeout) com checagem de hierarquia
- **Advertências**: histórico persistente por servidor (`/avisar`, `/avisos`)
- **Limpeza**: apagar mensagens em massa, com filtro por autor
- **Canal**: modo lento, trancar/destrancar
- **Auditoria**: toda ação registrada no canal de logs

### 🎖️ Automação de Cargos
- **Cargos por nível**: recompensa automática ao subir de nível (estilo MEE6)
- **Autorole**: cargo concedido a quem entra no servidor
- **Painéis de cargo**: botões de auto-atribuição que sobrevivem ao restart

### 🛠️ Administração
- **Configuração por servidor**: canais de log, boas-vindas e level up
- **Cache de configuração**: evita ida ao banco em cada mensagem
- **Rate limit**: cooldown nos comandos de IA para não queimar cota da API
- **Logs de Moderação**: mensagens editadas/apagadas, entradas e saídas
- **API HTTP**: Controle remoto via endpoints REST
- **Dashboard Streamlit**: Interface visual para operações

---

## 🏗️ Arquitetura

```
┌──────────────────┐
│  Discord API     │
│  (Gateway)       │
└────────┬─────────┘
         │
         ▼
┌──────────────────────────────────┐
│      CLUTCH BOT (main.py)        │
│                                  │
│  ┌─────────┐  ┌─────────────┐  │
│  │  Cogs   │  │  Database   │  │
│  │(11 mods)│  │  (SQLite)   │  │
│  └─────────┘  └─────────────┘  │
└────────┬─────────────────────────┘
         │
         ├──► API HTTP (aiohttp:8080)
         │            │
         │            ▼
         │    ┌──────────────┐
         │    │  Dashboard   │
         │    │  (Streamlit) │
         │    └──────────────┘
         │
         └──► UDP Audio Streams
                     │
              ┌──────┴──────┐
              ▼             ▼
        [receptor.py]  [microfone.py]
```

### Sistema de Áudio em Tempo Real

```
Microfone (Windows)
       │ pyaudio
       ▼
 [dashboard.py]
       │ UDP:6001
       ▼
   API Controle
       │
       ▼
   MixerSource ◄──── Soundboard (MP3)
       │
       ▼
  Discord Voice ────► Discord Users
       │ UDP:6000
       ▼
  [receptor.py] ──► Speakers (Windows)
```

---

## 🔧 Pré-requisitos

### Software Necessário

1. **Python 3.10+**
   - Download: https://www.python.org/downloads/
   - ⚠️ Marque "Add Python to PATH" durante instalação
   - No Python 3.13+ o módulo `audioop` foi removido; o bot usa `numpy` como
     fallback automático (já está em `requirements.txt`).

2. **FFmpeg** (para processamento de áudio)
   - Windows: https://www.geeksforgeeks.org/how-to-install-ffmpeg-on-windows/
   - Linux: `sudo apt install ffmpeg`
   - Mac: `brew install ffmpeg`

3. **PyAudio** — necessário apenas para dashboard/microfone/receptor,
   **não** para o bot. Exige a lib nativa `portaudio`:
   ```bash
   # Linux
   sudo apt install portaudio19-dev && pip install pyaudio
   # macOS
   brew install portaudio && pip install pyaudio
   # Windows
   pip install pipwin && pipwin install pyaudio
   ```

### Contas e Tokens

1. **Bot Discord**
   - Acesse: https://discord.com/developers/applications
   - Crie uma aplicação → Bot → Copie o Token
   - Ative **Privileged Gateway Intents**:
     - ✅ Presence Intent
     - ✅ Server Members Intent
     - ✅ Message Content Intent

2. **Google Gemini API Key** (opcional — sem ela os comandos de IA ficam desativados)
   - Acesse: https://aistudio.google.com/app/apikey
   - Crie uma API Key gratuita

---

## 📥 Instalação

### 1. Clone o Repositório
```bash
git clone https://github.com/alessandrolsdev/clutch-discord-bot.git
cd clutch-discord-bot
```

### 2. Crie Ambiente Virtual (recomendado)
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 3. Instale Dependências

As dependências são separadas: a lista do bot não inclui `pyaudio`
(que exige `portaudio` nativo e quebrava o `docker build`).

```bash
# Só o bot (é o que a imagem Docker usa)
pip install -r requirements.txt

# Bot + dashboard + microfone/receptor
pip install -r requirements-dashboard.txt
```

### 4. Configure o Ambiente
```bash
# Windows
copy .env.example .env && notepad .env

# Linux/Mac
cp .env.example .env && ${EDITOR:-nano} .env
```

### 5. Rode os Testes (opcional)
```bash
python -m unittest discover -s tests -t .
```

---

## ⚙️ Configuração

### Arquivo `.env`

`.env.example` lista todas as variáveis com comentários. O mínimo é:

```env
# Token do Bot Discord (obrigatório)
DISCORD_TOKEN=

# Chave da API de controle. Sem ela a API só escuta em 127.0.0.1.
# Gere com: python -c "import secrets; print(secrets.token_urlsafe(32))"
API_KEY=

# API Key do Google Gemini (opcional)
GEMINI_API_KEY=
```

### 🔒 Segurança da API de controle

A API HTTP (porta 8080) faz o bot **entrar em canais de voz e enviar
mensagens em seu nome**. Por isso:

- Sem `API_KEY`, o servidor sobe **apenas em `127.0.0.1`**.
- Para expor na rede (ex: Docker), defina `API_KEY` **e** `API_HOST=0.0.0.0`.
  Sem a chave, a API simplesmente não sobe e um erro é registrado no log.
- Todas as rotas exigem o header `X-API-Key`.
- No `docker-compose.yml` as portas são publicadas só em `127.0.0.1`.

```bash
curl -H "X-API-Key: $API_KEY" http://127.0.0.1:8080/status
```

### Permissões do Bot (OAuth2)

Ao convidar o bot para seu servidor, use este link:

```
https://discord.com/oauth2/authorize?client_id=SEU_CLIENT_ID&permissions=3213312&scope=bot%20applications.commands
```

⚠️ Evite `permissions=8` (Administrador). O bot só precisa de:
- ✅ Ler/Enviar Mensagens + Embed Links
- ✅ Conectar/Falar em Canais de Voz
- ✅ Ver Histórico de Mensagens
- ✅ Usar Slash Commands (`applications.commands`)

---

## 🚀 Uso

### 🆕 Launcher Unificado (Recomendado)

A partir da v3.0, use o **script de inicialização unificado** que gerencia todos os componentes:

```bash
python start.py
```

**Modos disponíveis:**

```bash
# Menu interativo (escolha os componentes)
python start.py

# Inicia tudo automaticamente
python start.py --all

# Apenas o bot Discord
python start.py --bot-only

# Modo desenvolvimento (mostra logs em tempo real)
python start.py --dev
```

**O que o launcher faz:**
- ✅ Verifica dependências (Python, FFmpeg, Docker, PyAudio)
- ✅ Cria arquivo `.env` se não existir
- ✅ Inicia componentes selecionados (Docker, Bot, Dashboard, Receptor, Microfone)
- ✅ Monitora saúde dos processos
- ✅ Shutdown gracioso com Ctrl+C

---

### 💾 Modo Manual (Avançado)

Se preferir iniciar componentes individualmente:

#### Iniciar o Bot
```bash
python main.py
```

Saída esperada:
```
[INFO] 💾 Banco de dados inicializado em data/clutch.db
[INFO] ⚙️  Cog carregado: api_controle.py
[INFO] ⚙️  Cog carregado: audio.py
...
[INFO] Cogs: 11 carregados, 0 com falha
[INFO] 🌲 23 slash commands sincronizados
[INFO] 🌐 API de controle online em http://127.0.0.1:8080
[INFO] ✅ CLUTCH v3.0 ONLINE como ClutchBot (1 servidores)
```

#### Iniciar Dashboard (Opcional)
```bash
streamlit run dashboard.py
```
O dashboard lê `API_KEY_1`/`API_KEY_2` (ou `API_KEY`) do ambiente para
autenticar na API do bot.

#### Iniciar Receptor de Áudio (Opcional)
```bash
python receptor.py
```

#### Iniciar Microfone (Opcional)
```bash
python microfone.py
```

---

## 🎮 Comandos Principais

### Música e Áudio
| Comando | Descrição | Exemplo |
|---------|-----------|---------|
| `/play <busca>` | Toca ou enfileira (aceita playlist) | `/play lofi hip hop` |
| `/fila [pagina]` | Mostra a fila de reprodução | `/fila 2` |
| `/tocando` | Faixa atual com barra de progresso | `/tocando` |
| `/pular` | Pula para a próxima faixa | `/pular` |
| `/loop <modo>` | Repetir faixa ou fila | `/loop queue` |
| `/embaralhar` | Embaralha a fila | `/embaralhar` |
| `/remover <n>` | Remove uma faixa da fila | `/remover 3` |
| `/mover <a> <b>` | Reordena a fila | `/mover 5 1` |
| `/limparfila` | Esvazia a fila | `/limparfila` |
| `/volume <0-150>` | Ajusta o volume | `/volume 80` |
| `/pausar` · `/retomar` | Pausa e retoma | `/pausar` |
| `/stop` | Para tudo e sai da call | `/stop` |
| `/sfx <nome>` | Toca efeito sonoro | `/sfx alarme` |
| `/diga <texto>` | Fala em voz alta (TTS) | `/diga Olá pessoal!` |
| `/entrar` · `/sair` | Entra/sai do canal de voz | `/entrar` |

> 🎧 **Controle da fila**: sozinho na call, qualquer um controla. Com mais gente,
> só quem tem o cargo DJ ou permissão de "Gerenciar Canais" mexe na fila alheia.

### Inteligência Artificial
| Comando | Descrição | Exemplo |
|---------|-----------|---------|
| `/chat <msg>` | Conversa com memória | `/chat Como está o clima?` |
| `/persona <tipo>` | Muda personalidade (por servidor) | `/persona hacker` |
| `/esquecer` | Limpa seu histórico de chat | `/esquecer` |
| `/rpg [@user]` | Gera ficha de RPG | `/rpg @João` |
| `/vibe` | Julga vibe da call | `/vibe` |
| `/shipp <@A> <@B>` | Testa compatibilidade | `/shipp @Ana @Pedro` |

### Social e Gamificação
| Comando | Descrição | Exemplo |
|---------|-----------|---------|
| `/perfil [@user]` | Ver card de jogador | `/perfil` |
| `/bio <texto>` | Mudar biografia | `/bio Sou dev backend!` |
| `/ranking` | Top 10 do servidor | `/ranking` |
| `/noticias` | Jornal do servidor (IA) | `/noticias` |

> ⏳ Os comandos de IA têm cooldown por usuário (`/chat` 3×/min, demais 2×/min)
> para não estourar a cota do Gemini.

### Utilidades
| Comando | Descrição | Exemplo |
|---------|-----------|---------|
| `/ping` | Verifica latência | `/ping` |
| `/avatar [@user]` | Mostra avatar ampliado | `/avatar @User` |
| `/ajuda` | Menu interativo de ajuda | `/ajuda` |
| `/status` | Saúde do bot, DB, API e recursos | `/status` |
| `/uptime` | Tempo online | `/uptime` |
| `/parar` | Interrompe qualquer som | `/parar` |

### Moderação
| Comando | Permissão | Descrição |
|---------|-----------|-----------|
| `/ban <membro>` | Banir Membros | Bane, com opção de apagar mensagens |
| `/unban <id>` | Banir Membros | Remove um banimento pelo ID |
| `/kick <membro>` | Expulsar Membros | Expulsa do servidor |
| `/castigo <membro> <min>` | Moderar Membros | Timeout de até 28 dias |
| `/descastigo <membro>` | Moderar Membros | Libera antes da hora |
| `/avisar <membro>` | Moderar Membros | Registra uma advertência |
| `/avisos [membro]` | — | Histórico de advertências |
| `/removeraviso <id>` | Moderar Membros | Apaga uma advertência |
| `/limparavisos <membro>` | Gerenciar Servidor | Zera o histórico |
| `/limpar <n> [membro]` | Gerenciar Mensagens | Apaga mensagens em massa |
| `/lento <seg>` | Gerenciar Canais | Modo lento |
| `/trancar` · `/destrancar` | Gerenciar Canais | Fecha/abre o canal |

Toda punição respeita a hierarquia de cargos, avisa o punido por DM e é
registrada no canal de `/setlog`.

### Automod
| Comando | Descrição |
|---------|-----------|
| `/automod ativar <true\|false>` | Liga ou desliga a moderação automática |
| `/automod ver` | Mostra todas as regras e isenções |
| `/automod regras` | Ajusta spam, flood, links, menções, CAPS, castigo |
| `/automod palavra <ação>` | Adiciona, remove ou lista palavras proibidas |
| `/automod isentar <canal\|cargo>` | Isenta um canal ou cargo |

**Como funciona a punição escalonada:**
1. A mensagem é apagada e o autor recebe um aviso que some em 8 segundos
2. Uma advertência entra no mesmo histórico do `/avisar`
3. A cada N advertências (padrão 3), o autor leva castigo automático

**Padrões:** 5 mensagens em 5s, 3 repetições iguais, convites bloqueados,
5 menções por mensagem, 70% de CAPS. Qualquer limite em `0` desliga a regra.
Links comuns são **permitidos** por padrão.

> 🛡️ Quem tem "Gerenciar Mensagens" nunca é pego pelo automod. Para o resto,
> use `/automod isentar` com o canal ou cargo.

Detalhes que evitam falso positivo: `assado` não dispara pela palavra `ass`
(a comparação é por palavra inteira), acentos são normalizados (`IDIÔTA` bate
com `idiota`), e URLs/menções saem da conta de CAPS antes da medição.

### Comandos do Dono (prefixo `!`, só para o dono da aplicação)
| Comando | Descrição |
|---------|-----------|
| `!sync` | Sincroniza os slash commands **neste servidor** (instantâneo) |
| `!sync global` | Sincroniza em todos os servidores (leva até 1h) |
| `!sync limpar` | Remove os comandos deste servidor |
| `!reload <cog>` | Recarrega um cog sem reiniciar o bot |
| `!cogs` | Lista os cogs carregados |
| `!backup` · `!backups` | Gera e lista backups do banco |
| `!cache [limpar]` | Estado do cache de configuração |
| `!info` | Resumo operacional |

> `!sync` é comando de prefixo de propósito: para usar um slash command ele
> precisa já estar sincronizado, e é justamente isso que o comando resolve.

### Cargos e Configuração
| Comando | Permissão | Descrição |
|---------|-----------|-----------|
| `/nivelcargo definir <nivel> <cargo>` | Gerenciar Cargos | Recompensa por nível |
| `/nivelcargo listar` · `remover` | Gerenciar Cargos | Gerencia as recompensas |
| `/autorole [cargo]` | Gerenciar Cargos | Cargo automático ao entrar |
| `/painelcargos <titulo> <cargos>` | Gerenciar Cargos | Painel com botões de cargo |
| `/removerpainel <id>` | Gerenciar Cargos | Desativa um painel |
| `/setlog [canal]` | Gerenciar Servidor | Canal de logs |
| `/boasvindas [canal]` | Gerenciar Servidor | Canal de boas-vindas |
| `/levelupcanal [canal]` | Gerenciar Servidor | Onde anunciar level ups |
| `/xpcanal [canal]` | Gerenciar Servidor | Liga/desliga XP num canal |
| `/xp <true\|false>` | Gerenciar Servidor | Liga/desliga a gamificação |

> 🔐 Os logs de mensagens apagadas/editadas só são publicados **depois** de
> configurar um canal com `/setlog`. Sem isso, o bot não republica nada —
> antes ele reexibia no canal público toda mensagem que alguém apagasse.

---

## 📊 Dashboard Web

### Funcionalidades

- 🎵 **Player de Música**: Faixa atual, progresso, fila e botões de pular/parar
- 🎙️ **Controle de Microfone**: Ativar/desativar transmissão
- 🎭 **Modulador de Voz**: Alterar voz em tempo real
- 🔊 **Soundboard**: Tocar efeitos sonoros remotamente
- 📡 **Status do Bot**: Ver membros conectados e quem está falando
- 🎛️ **Mixer de Volumes**: Ajustar níveis de mic e FX

### Acesso

Após iniciar `streamlit run dashboard.py`:
```
http://localhost:8501
```

---

## 📁 Estrutura do Projeto

```
clutch-discord-bot/
│
├── main.py                 # Ponto de entrada do bot
├── dashboard.py            # Interface web (Streamlit)
├── receptor.py             # Receptor de áudio UDP→Speakers
├── microfone.py            # Captura de microfone→UDP
│
├── cogs/                   # Módulos do bot (Cogs)
│   ├── api_controle.py    # API HTTP autenticada + MixerSource
│   ├── automod.py         # Moderação automática de mensagens
│   ├── admin.py           # !sync, !reload, !backup (dono do bot)
│   ├── audio.py           # TTS e reprodução de arquivos
│   ├── cargos.py          # Cargos por nível, autorole, painéis
│   ├── cerebro.py         # Chat IA + Personas
│   ├── geral.py           # Comandos utilitários
│   ├── iconico.py         # RPG, Vibe, Shipp (IA divertida)
│   ├── moderacao.py       # Ban, kick, castigo, avisos, limpeza
│   ├── monitoring.py      # Health checks (/status, /ping, /uptime)
│   ├── musica.py          # Player com fila
│   ├── porteiro.py        # Sistema de boas-vindas
│   ├── presence_bridge.py # Ingestão de presença para o CLUTCH
│   ├── social.py          # XP, Níveis, Perfis
│   └── vigia.py           # Logs de moderação
│
├── config/
│   └── settings.py        # Configuração central (lê o .env)
│
├── utils/
│   ├── ai.py              # Cliente Gemini assíncrono
│   ├── audio_mix.py       # Mixagem PCM (funções puras)
│   ├── automod.py         # Regras de automod (funções puras)
│   ├── guild_config.py    # Cache de configuração por servidor
│   ├── logger.py          # Logging rotacionado
│   ├── musica_fila.py     # Fila de reprodução (funções puras)
│   ├── presence_bridge.py # Cliente da bridge de presença
│   └── soundboard.py      # Resolução segura de nomes de sons
│
├── infra/
│   ├── backup.py          # Backup consistente do SQLite
│   └── database.py        # Gerenciador do SQLite
│
├── scripts/
│   └── verificar_cogs.py  # Checa carregamento e nomes duplicados
│
├── .github/workflows/
│   └── ci.yml             # Testes, lint e build da imagem
│
├── tests/                 # Testes (python -m unittest discover -s tests -t .)
│
├── assets/
│   └── sfx/               # Arquivos de efeitos sonoros (.mp3)
│
├── data/
│   └── clutch.db          # Banco de dados (criado automaticamente)
│
├── temp/                  # Arquivos temporários (músicas, TTS)
│
├── requirements.txt           # Dependências do bot
├── requirements-dashboard.txt # + dashboard/microfone/receptor
├── .dockerignore              # Impede .env e data/ de entrar na imagem
├── .env                       # Configurações (NÃO VERSIONAR)
├── .env.example           # Template de configuração
├── .gitignore            
└── README.md              # Este arquivo
```

---

## 🚀 Configuração Recomendada (primeiros 5 minutos)

Depois de convidar o bot, rode estes comandos no servidor:

```
/setlog #logs-do-servidor        → liga os logs de moderação
/boasvindas #geral               → mensagens de entrada
/levelupcanal #conquistas        → anúncios de level up longe do chat
/xpcanal #comandos-do-bot        → não dar XP em canal de spam
/nivelcargo definir 5 @Ativo     → recompensa de cargo no nível 5
/autorole @Membro                → cargo automático para quem entra
/painelcargos "Escolha seus times" @Valorant @LoL @CS
/automod ativar true             → moderação automática
/automod isentar #divulgacao     → libera links num canal só
```

> ⚠️ Para os cargos funcionarem, **o cargo do bot precisa estar acima** dos
> cargos que ele vai conceder na lista de cargos do servidor. Os comandos
> avisam quando isso não está certo.

---

## ❗ Troubleshooting

### Erro: "Token não encontrado no .env"
**Solução**: Certifique-se de criar o arquivo `.env` (copie de `.env.example`) e adicionar seu `DISCORD_TOKEN`.

### Erro: "FFmpeg not found"
**Solução**: Instale FFmpeg e adicione ao PATH do sistema.

### Erro: "No module named 'pyaudio'"
PyAudio só é necessário para dashboard/microfone/receptor:
```bash
pip install -r requirements-dashboard.txt
```
Se a compilação falhar, instale antes a lib nativa `portaudio`
(ver Pré-requisitos).

### Bot não responde a comandos
**Solução**: 
1. Verifique se os **Intents** estão ativados no Discord Developer Portal
2. Aguarde alguns segundos após iniciar (sincronização de slash commands)
3. Verifique logs do terminal

### Dashboard não conecta ao bot
**Solução**:
1. Certifique-se de que o bot está rodando (`python main.py`)
2. Procure `🌐 API de controle online` nos logs
3. Se aparecer `API HTTP NÃO iniciada`, você definiu `API_HOST` público sem
   `API_KEY` — defina a chave ou volte para `API_HOST=127.0.0.1`
4. Erro 401 no dashboard: a `API_KEY` do dashboard não bate com a do bot
5. Porta 8080 em uso: mude `API_PORT` no `.env`

### O bot não concede os cargos por nível
1. O cargo do bot precisa estar **acima** do cargo concedido
2. O bot precisa da permissão "Gerenciar Cargos"
3. Confira as recompensas com `/nivelcargo listar`

### Os botões do painel de cargos pararam de funcionar
Os painéis são restaurados no startup a partir do banco. Se o `data/clutch.db`
foi apagado, crie o painel de novo com `/painelcargos`.

### `/sfx` não encontra nenhum som
Coloque os arquivos `.mp3` em `assets/sfx/` (ou no diretório definido em
`SOUNDS_DIR`). O comando `/sfx` e a rota `POST /play` usam a **mesma** pasta.

### Áudio robótico/travando no Discord
**Solução**:
- Reduza `AUDIO_CHUNK_SIZE` no `.env` para menos latência
- Verifique sua conexão de internet
- Aumente `RECEPTOR_BUFFER_SIZE` no `.env` para mais estabilidade

---

## 🧪 Desenvolvimento

### Rodando os testes
```bash
python -m unittest discover -s tests -t .     # 108 testes
python scripts/verificar_cogs.py              # carrega os cogs, checa duplicados
python -m pyflakes .                          # lint
```

O CI (`.github/workflows/ci.yml`) roda os três a cada push, em Python 3.11 e
3.12, e ainda constrói a imagem Docker.

### Sync rápido durante o desenvolvimento
O sync global leva até uma hora para propagar. Para desenvolver, aponte o bot
a um servidor de teste:

```env
DEV_GUILD_ID=123456789012345678
AUTO_SYNC=true
```

Os comandos passam a aparecer instantaneamente. Em produção, deixe
`DEV_GUILD_ID` vazio. Se estiver reiniciando muito, use `AUTO_SYNC=false` e
rode `!sync` quando precisar — o sync global tem rate limit apertado.

### Backups
Backup diário automático em `backups/`, mantendo os 7 mais recentes. Use
`!backup` para gerar na hora e `!backups` para listar.

A cópia usa a API `backup()` do SQLite, não um `cp`: com WAL ligado, copiar só
o arquivo `.db` durante uma escrita perde os dados mais recentes.

Para restaurar (**com o bot parado**):
```python
python -c "from infra.backup import restaurar_backup; \
  restaurar_backup('backups/clutch-backup-AAAAMMDD-HHMMSS.db', 'data/clutch.db')"
```
O banco atual é preservado como `data/clutch.db.antes-da-restauracao`.

---

## 🤝 Contribuindo

Contribuições são bem-vindas! Para contribuir:

1. Fork o projeto
2. Crie uma branch para sua feature (`git checkout -b feature/MinhaFeature`)
3. Commit suas mudanças (`git commit -m 'Adiciona MinhaFeature'`)
4. Push para a branch (`git push origin feature/MinhaFeature`)
5. Abra um Pull Request

### Diretrizes

- Mantenha a documentação em **PT-BR**
- Adicione **docstrings** em todas as funções públicas
- Siga o padrão de código existente (PEP 8)
- Teste suas alterações antes de enviar

---

## 📝 Licença

Este projeto está sob a licença. Veja o arquivo `LICENSE` para mais detalhes.

---

## 👤 Autor

**Clutch Development Team**

- Discord: [norbiom](https://discord.com/users/norbiom)
- GitHub: [alessandrolsdev](https://github.com/alessandrolsdev)

---

## 🙏 Agradecimentos

- **Discord.py** - Framework do bot
- **Google Gemini** - IA generativa
- **yt-dlp** - Reprodução de músicas
- **Streamlit** - Dashboard web
- **Pedalboard (Spotify)** - Processamento de áudio profissional

---

<div align="center">

Desenvolvido com ❤️ por alessandrolsdev

[⬆ Voltar ao topo](#-clutch-discord-bot-v30)

</div>
