"""
CLUTCH BOT - LAUNCHER UNIFICADO
================================

Script de inicialização que orquestra todos os componentes do bot:
- 🐳 Docker Compose (agentes de espionagem)
- 🤖 Bot Discord (main.py)
- 🎙️ Microfone (microfone.py)
- 🔊 Receptor de Áudio (receptor.py)
- 📊 Dashboard Web (dashboard.py)

Uso:
    python start.py              # Menu interativo
    python start.py --all        # Inicia tudo
    python start.py --bot-only   # Só o bot
    python start.py --dev        # Modo desenvolvimento

Autor: Clutch Development Team
Versão: 3.0
"""

import os
import sys
import subprocess
import time
import argparse
import platform
from pathlib import Path
from typing import List, Optional, Dict
import shutil
from dataclasses import dataclass
from enum import Enum


# Cores para terminal
class Color:
    """Códigos ANSI para colorir output no terminal"""

    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


class ComponentStatus(Enum):
    """Estados possíveis de um componente"""

    STOPPED = "⚫"
    STARTING = "🟡"
    RUNNING = "🟢"
    ERROR = "🔴"


@dataclass
class Component:
    """Representa um componente do sistema"""

    name: str
    command: List[str]
    description: str
    required: bool = False
    process: Optional[subprocess.Popen] = None
    status: ComponentStatus = ComponentStatus.STOPPED
    port: Optional[int] = None
    health_check_url: Optional[str] = None


class ClutchLauncher:
    """Gerenciador de inicialização e shutdown do Clutch Bot"""

    def __init__(self, dev_mode: bool = False):
        self.dev_mode = dev_mode
        self.components: Dict[str, Component] = {}
        self.base_dir = Path(__file__).parent
        self.is_windows = platform.system() == "Windows"

        # Define componentes disponíveis
        self._setup_components()

    def _setup_components(self):
        """Configura todos os componentes do sistema"""

        # Determina executável Python correto
        python_exe = "python" if self.is_windows else "python3"

        self.components = {
            "docker": Component(
                name="Docker Compose",
                command=["docker-compose", "up", "-d"],
                description="Containers dos agentes de espionagem",
                required=False,
                port=8080,
                health_check_url="http://localhost:8080/status",
            ),
            "bot": Component(
                name="Discord Bot",
                command=[python_exe, "main.py"],
                description="Bot principal do Discord",
                required=True,
            ),
            "receptor": Component(
                name="Receptor de Áudio",
                command=[python_exe, "receptor.py"],
                description="Recebe áudio UDP e toca nos speakers",
                required=False,
            ),
            "microfone": Component(
                name="Microfone",
                command=[python_exe, "microfone.py"],
                description="Captura microfone e envia via UDP",
                required=False,
            ),
            "dashboard": Component(
                name="Dashboard Web",
                command=["streamlit", "run", "dashboard.py"],
                description="Interface web de controle",
                required=False,
                port=8501,
                health_check_url="http://localhost:8501",
            ),
        }

    def print_banner(self):
        """Exibe banner de boas-vindas"""
        banner = f"""
{Color.CYAN}╔══════════════════════════════════════════════╗
║                                              ║
║       🤖 CLUTCH DISCORD BOT V3.0 🤖          ║
║                                              ║
║     Launcher Unificado de Componentes        ║
║                                              ║
╚══════════════════════════════════════════════╝{Color.ENDC}
"""
        print(banner)

    def check_dependencies(self) -> bool:
        """Verifica se todas as dependências estão instaladas"""
        print(f"\n{Color.BOLD}🔍 Verificando dependências...{Color.ENDC}\n")

        dependencies = {
            "Python": ["python", "--version"],
            "FFmpeg": ["ffmpeg", "-version"],
            "Docker": ["docker", "--version"],
            "Docker Compose": ["docker-compose", "--version"],
        }

        all_ok = True

        for name, cmd in dependencies.items():
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    version = result.stdout.split("\n")[0]
                    print(f"  ✅ {name}: {Color.GREEN}{version}{Color.ENDC}")
                else:
                    raise Exception()
            except:
                if name in ["Docker", "Docker Compose"]:
                    print(
                        f"  ⚠️  {name}: {Color.YELLOW}Não encontrado (opcional){Color.ENDC}"
                    )
                else:
                    print(f"  ❌ {name}: {Color.RED}NÃO INSTALADO{Color.ENDC}")
                    all_ok = False

        # Verifica PyAudio
        try:
            import pyaudio

            print(f"  ✅ PyAudio: {Color.GREEN}Instalado{Color.ENDC}")
        except ImportError:
            print(
                f"  ⚠️  PyAudio: {Color.YELLOW}Não instalado (necessário para áudio){Color.ENDC}"
            )

        return all_ok

    def check_env_file(self) -> bool:
        """Verifica se arquivo .env existe e está configurado"""
        env_path = self.base_dir / ".env"
        env_example = self.base_dir / ".env.example"

        if not env_path.exists():
            print(f"\n{Color.YELLOW}⚠️  Arquivo .env não encontrado!{Color.ENDC}\n")

            if env_example.exists():
                response = input(
                    f"   Deseja criar .env a partir de .env.example? (s/n): "
                )
                if response.lower() == "s":
                    shutil.copy(env_example, env_path)
                    print(f"   {Color.GREEN}✅ Arquivo .env criado!{Color.ENDC}")
                    print(
                        f"   {Color.YELLOW}⚠️  ATENÇÃO: Configure seus tokens no arquivo .env{Color.ENDC}\n"
                    )

                    # Abre o arquivo no editor padrão
                    if self.is_windows:
                        os.system(f'notepad "{env_path}"')
                    else:
                        os.system(
                            f'nano "{env_path}" || vim "{env_path}" || vi "{env_path}"'
                        )

                    return True
                else:
                    print(
                        f"   {Color.RED}❌ Não é possível iniciar sem .env{Color.ENDC}\n"
                    )
                    return False
            else:
                print(
                    f"   {Color.RED}❌ .env.example também não encontrado!{Color.ENDC}\n"
                )
                return False

        # Verifica se TOKEN está configurado
        with open(env_path, "r", encoding="utf-8") as f:
            content = f.read()
            if "seu_token_aqui" in content or "DISCORD_TOKEN=" not in content:
                print(
                    f"   {Color.YELLOW}⚠️  DISCORD_TOKEN parece não estar configurado{Color.ENDC}\n"
                )
                return False

        return True

    def start_component(self, component: Component) -> bool:
        """Inicia um componente individual"""
        print(
            f"  {ComponentStatus.STARTING.value} Iniciando {component.name}...", end=" "
        )
        component.status = ComponentStatus.STARTING

        try:
            # Ajusta comando para Docker
            if component.name == "Docker Compose":
                # Para nas portas específicas primeiro se já estiver rodando
                subprocess.run(
                    ["docker-compose", "down"], capture_output=True, timeout=10
                )

            # Inicia o processo
            if self.dev_mode:
                # Em modo dev, mostra output diretamente
                component.process = subprocess.Popen(
                    component.command, cwd=self.base_dir
                )
            else:
                # Em modo produção, redireciona output para arquivo de log
                log_dir = self.base_dir / "logs"
                log_dir.mkdir(exist_ok=True)

                log_file = log_dir / f"{component.name.lower().replace(' ', '_')}.log"

                with open(log_file, "w") as log:
                    component.process = subprocess.Popen(
                        component.command,
                        cwd=self.base_dir,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                    )

            # Aguarda um pouco para verificar se não falhou imediatamente
            time.sleep(2)

            if component.process.poll() is None:
                component.status = ComponentStatus.RUNNING
                print(f"{Color.GREEN}OK{Color.ENDC}")
                return True
            else:
                component.status = ComponentStatus.ERROR
                print(f"{Color.RED}FALHOU{Color.ENDC}")
                return False

        except FileNotFoundError:
            component.status = ComponentStatus.ERROR
            print(f"{Color.RED}COMANDO NÃO ENCONTRADO{Color.ENDC}")
            return False
        except Exception as e:
            component.status = ComponentStatus.ERROR
            print(f"{Color.RED}ERRO: {e}{Color.ENDC}")
            return False

    def stop_component(self, component: Component):
        """Para um componente individual"""
        if component.process:
            print(f"  🛑 Parando {component.name}...", end=" ")

            try:
                if component.name == "Docker Compose":
                    subprocess.run(["docker-compose", "down"], timeout=10)
                else:
                    component.process.terminate()
                    component.process.wait(timeout=5)

                component.status = ComponentStatus.STOPPED
                print(f"{Color.GREEN}OK{Color.ENDC}")
            except subprocess.TimeoutExpired:
                print(f"{Color.YELLOW}FORÇANDO...{Color.ENDC}", end=" ")
                component.process.kill()
                component.status = ComponentStatus.STOPPED
                print(f"{Color.GREEN}OK{Color.ENDC}")

    def start_all(self, components_to_start: List[str]):
        """Inicia componentes selecionados"""
        print(f"\n{Color.BOLD}🚀 Iniciando componentes...{Color.ENDC}\n")

        success_count = 0

        for comp_id in components_to_start:
            component = self.components.get(comp_id)
            if component:
                if self.start_component(component):
                    success_count += 1
                time.sleep(1)  # Delay entre inicializações

        print(
            f"\n{Color.GREEN}✅ {success_count}/{len(components_to_start)} componentes iniciados com sucesso!{Color.ENDC}\n"
        )

        if success_count > 0:
            self.show_status()

    def stop_all(self):
        """Para todos os componentes em execução"""
        print(f"\n{Color.BOLD}🛑 Encerrando componentes...{Color.ENDC}\n")

        for component in self.components.values():
            if component.status == ComponentStatus.RUNNING:
                self.stop_component(component)

        print(f"\n{Color.GREEN}✅ Todos os componentes foram encerrados{Color.ENDC}\n")

    def show_status(self):
        """Mostra status atual de todos os componentes"""
        print(f"{Color.BOLD}📊 Status dos Componentes:{Color.ENDC}\n")

        for component in self.components.values():
            status_icon = component.status.value
            status_text = component.status.name

            color = {
                ComponentStatus.RUNNING: Color.GREEN,
                ComponentStatus.STARTING: Color.YELLOW,
                ComponentStatus.ERROR: Color.RED,
                ComponentStatus.STOPPED: Color.ENDC,
            }.get(component.status, Color.ENDC)

            port_info = f" (:{component.port})" if component.port else ""
            print(
                f"  {status_icon} {component.name}{port_info}: {color}{status_text}{Color.ENDC}"
            )
            print(f"     {Color.CYAN}{component.description}{Color.ENDC}")

    def interactive_menu(self):
        """Menu interativo para selecionar componentes"""
        self.print_banner()

        # Verificações iniciais
        if not self.check_dependencies():
            print(
                f"\n{Color.RED}❌ Dependências faltando. Por favor, instale antes de continuar.{Color.ENDC}\n"
            )
            return

        if not self.check_env_file():
            print(
                f"\n{Color.RED}❌ Arquivo .env não configurado. Configure antes de continuar.{Color.ENDC}\n"
            )
            return

        print(f"\n{Color.BOLD}Selecione os componentes para iniciar:{Color.ENDC}\n")

        print("  1. 🐳 Docker Compose (agentes)")
        print("  2. 🤖 Bot Discord (obrigatório)")
        print("  3. 🔊 Receptor de Áudio")
        print("  4. 🎙️ Microfone")
        print("  5. 📊 Dashboard Web")
        print(f"\n  {Color.GREEN}A. Iniciar TODOS os componentes{Color.ENDC}")
        print(f"  {Color.CYAN}B. Apenas Bot + Dashboard (recomendado){Color.ENDC}")
        print(f"  {Color.YELLOW}Q. Sair{Color.ENDC}\n")

        choice = input("Sua escolha: ").strip().upper()

        components_map = {
            "1": ["docker"],
            "2": ["bot"],
            "3": ["receptor"],
            "4": ["microfone"],
            "5": ["dashboard"],
            "A": ["docker", "bot", "receptor", "microfone", "dashboard"],
            "B": ["bot", "dashboard"],
        }

        if choice == "Q":
            print("\n👋 Até logo!\n")
            return

        components_to_start = components_map.get(choice, ["bot"])

        try:
            self.start_all(components_to_start)

            # Mantém rodando e aguarda Ctrl+C
            print(
                f"\n{Color.GREEN}✨ Sistema rodando! Pressione Ctrl+C para encerrar.{Color.ENDC}\n"
            )

            while True:
                time.sleep(1)

        except KeyboardInterrupt:
            print(f"\n\n{Color.YELLOW}⚠️  Interrupção detectada...{Color.ENDC}")
            self.stop_all()


def main():
    """Ponto de entrada principal"""
    parser = argparse.ArgumentParser(description="Clutch Bot Launcher")
    parser.add_argument(
        "--all", action="store_true", help="Inicia todos os componentes"
    )
    parser.add_argument("--bot-only", action="store_true", help="Inicia apenas o bot")
    parser.add_argument(
        "--dev", action="store_true", help="Modo desenvolvimento (mostra logs)"
    )

    args = parser.parse_args()

    launcher = ClutchLauncher(dev_mode=args.dev)

    if args.all:
        launcher.print_banner()
        launcher.start_all(["docker", "bot", "receptor", "microfone", "dashboard"])
        try:
            print(
                f"\n{Color.GREEN}✨ Sistema rodando! Pressione Ctrl+C para encerrar.{Color.ENDC}\n"
            )
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            launcher.stop_all()

    elif args.bot_only:
        launcher.print_banner()
        launcher.start_all(["bot"])
        try:
            print(
                f"\n{Color.GREEN}✨ Bot rodando! Pressione Ctrl+C para encerrar.{Color.ENDC}\n"
            )
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            launcher.stop_all()

    else:
        # Menu interativo
        launcher.interactive_menu()


if __name__ == "__main__":
    main()
