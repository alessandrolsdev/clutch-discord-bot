# 🤖 Clutch Discord Bot V2.5

<div align="center">

Bot Discord avançado com **Inteligência Artificial**, **Sistema de Áudio em Tempo Real**, **Gamificação** e **Dashboard Web**.

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/downloads/)
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
- **Reprodução de Música**: Busca e toca músicas do YouTube com botões interativos
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

### 🛠️ Administração
- **Sistema de Boas-Vindas**: Mensagens automáticas para novos membros
- **Logs de Moderação**: Rastreamento de mensagens editadas/apagadas
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
│  │ (9 mods)│  │  (SQLite)   │  │
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

1. **Python 3.8+**
   - Download: https://www.python.org/downloads/
   - ⚠️ Marque "Add Python to PATH" durante instalação

2. **FFmpeg** (para processamento de áudio)
   - Windows: https://www.geeksforgeeks.org/how-to-install-ffmpeg-on-windows/
   - Linux: `sudo apt install ffmpeg`
   - Mac: `brew install ffmpeg`

3. **PyAudio** (requer instalação manual no Windows)
   ```bash
   # Windows: Baixe o wheel apropriado
   # https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio
   # Exemplo para Python 3.11 64-bit:
   pip install PyAudio-0.2.13-cp311-cp311-win_amd64.whl
   ```

### Contas e Tokens

1. **Bot Discord**
   - Acesse: https://discord.com/developers/applications
   - Crie uma aplicação → Bot → Copie o Token
   - Ative **Privileged Gateway Intents**:
     - ✅ Presence Intent
     - ✅ Server Members Intent
     - ✅ Message Content Intent

2. **Google Gemini API Key**
   - Acesse: https://makersuite.google.com/app/apikey
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
```bash
pip install -r requirements.txt
```

### 4. Configure o Ambiente
```bash
# Copie o arquivo de exemplo
copy .env.example .env

# Edite .env com seus tokens
notepad .env
```

---

## ⚙️ Configuração

### Arquivo `.env`

```env
# Token do Bot Discord
DISCORD_TOKEN=seu_token_aqui

# API Key do Google Gemini
GEMINI_API_KEY=sua_api_key_aqui

# (Opcional) Configurações de Áudio
UDP_TARGET_IP=127.0.0.1
UDP_PORT_ENVIO=6000
UDP_PORT_RECEBIMENTO=6001
```

### Permissões do Bot (OAuth2)

Ao convidar o bot para seu servidor, use este link:

```
https://discord.com/oauth2/authorize?client_id=1441450379886727221&permissions=8&integration_type=0&scope=bot
```

Permissões necessárias:
- ✅ Ler/Enviar Mensagens
- ✅ Conectar/Falar em Canais de Voz
- ✅ Gerenciar Mensagens (logs)
- ✅ Usar Slash Commands

---

## 🚀 Uso

### Iniciar o Bot
```bash
python main.py
```

Saída esperada:
```
⚙️  Cog Carregado: audio.py
⚙️  Cog Carregado: cerebro.py
⚙️  Cog Carregado: social.py
...
🌲 Slash Commands Sincronizados!
---
✅ CLUTCH V2.5 ONLINE: ClutchBot
💾 Banco de Dados SQL inicializado com sucesso!
---
```

### Iniciar Dashboard (Opcional)
```bash
streamlit run dashboard.py
```

### Iniciar Receptor de Áudio (Opcional)
```bash
python receptor.py
```

---

## 🎮 Comandos Principais

### Música e Áudio
| Comando | Descrição | Exemplo |
|---------|-----------|---------|
| `/play <busca>` | Toca música do YouTube | `/play lofi hip hop` |
| `/stop` | Para a música | `/stop` |
| `/sfx <nome>` | Toca efeito sonoro | `/sfx alarme` |
| `/diga <texto>` | Fala em voz alta (TTS) | `/diga Olá pessoal!` |
| `/entrar` | Entra no seu canal de voz | `/entrar` |
| `/sair` | Sai do canal de voz | `/sair` |

### Inteligência Artificial
| Comando | Descrição | Exemplo |
|---------|-----------|---------|
| `/chat <msg>` | Conversa com memória | `/chat Como está o clima?` |
| `/persona <tipo>` | Muda personalidade | `/persona hacker` |
| `/rpg [@user]` | Gera ficha de RPG | `/rpg @João` |
| `/vibe` | Julga vibe da call | `/vibe` |
| `/shipp <@A> <@B>` | Testa compatibilidade | `/shipp @Ana @Pedro` |

### Social e Gamificação
| Comando | Descrição | Exemplo |
|---------|-----------|---------|
| `/perfil [@user]` | Ver card de jogador | `/perfil` |
| `/bio <texto>` | Mudar biografia | `/bio Sou dev backend!` |
| `/noticias` | Jornal do servidor (IA) | `/noticias` |

### Utilidades
| Comando | Descrição | Exemplo |
|---------|-----------|---------|
| `/ping` | Verifica latência | `/ping` |
| `/avatar [@user]` | Mostra avatar ampliado | `/avatar @User` |
| `/ajuda` | Menu interativo de ajuda | `/ajuda` |

---

## 📊 Dashboard Web

### Funcionalidades

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
│   ├── api_controle.py    # API HTTP + MixerSource
│   ├── audio.py           # TTS e reprodução de arquivos
│   ├── cerebro.py         # Chat IA + Personas
│   ├── geral.py           # Comandos utilitários
│   ├── iconico.py         # RPG, Vibe, Shipp (IA divertida)
│   ├── musica.py          # YouTube player
│   ├── porteiro.py        # Sistema de boas-vindas
│   ├── social.py          # XP, Níveis, Perfis
│   └── vigia.py           # Logs de moderação
│
├── infra/
│   └── database.py        # Gerenciador do SQLite
│
├── assets/
│   └── sfx/               # Arquivos de efeitos sonoros (.mp3)
│
├── data/
│   └── clutch.db          # Banco de dados (criado automaticamente)
│
├── temp/                  # Arquivos temporários (músicas, TTS)
│
├── requirements.txt       # Dependências Python
├── .env                   # Configurações (NÃO VERSIONAR)
├── .env.example           # Template de configuração
├── .gitignore            
└── README.md              # Este arquivo
```

---

## ❗ Troubleshooting

### Erro: "Token não encontrado no .env"
**Solução**: Certifique-se de criar o arquivo `.env` (copie de `.env.example`) e adicionar seu `DISCORD_TOKEN`.

### Erro: "FFmpeg not found"
**Solução**: Instale FFmpeg e adicione ao PATH do sistema.

### Erro: "No module named 'PyAudio'"
**Solução (Windows)**:
1. Baixe o wheel correto: https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio
2. Instale: `pip install PyAudio-0.2.13-cpXX-cpXX-win_amd64.whl`

### Bot não responde a comandos
**Solução**: 
1. Verifique se os **Intents** estão ativados no Discord Developer Portal
2. Aguarde alguns segundos após iniciar (sincronização de slash commands)
3. Verifique logs do terminal

### Dashboard não conecta ao bot
**Solução**:
1. Certifique-se de que o bot está rodando (`python main.py`)
2. Verifique se a API está ativa (procure "API V8 ONLINE" nos logs)
3. Porta 8080 pode estar em uso - altere em `api_controle.py`

### Áudio robótico/travando no Discord
**Solução**:
- Reduza `CHUNK` em `microfone.py` para menos latência
- Verifique sua conexão de internet
- Aumente `TAMANHO_DO_BUFFER` em `receptor.py` para mais estabilidade

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

[⬆ Voltar ao topo](#-clutch-discord-bot-v25)

</div>
