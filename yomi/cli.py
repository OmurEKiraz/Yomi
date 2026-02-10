import os
import json
import logging
import time
import rich_click as click
from datetime import timedelta
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table
from rich import box
from rich.panel import Panel
from rich.text import Text

# --- Core Module Import ---
try:
    from .core import YomiCore
    from . import __version__ as VERSION
except ImportError:
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from yomi.core import YomiCore
    from yomi import __version__ as VERSION

APP_NAME = "YOMI CLI"

# --- 1. Console & Logging Setup ---
console = Console()
logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(console=console, rich_tracebacks=True, markup=True, show_path=False)]
)
logger = logging.getLogger("Yomi")

# --- 2. Rich Click Configuration ---
click.rich_click.USE_RICH_MARKUP = True
click.rich_click.STYLE_HEADER_TEXT = "bold magenta"
click.rich_click.STYLE_OPTION = "bold cyan"
click.rich_click.STYLE_COMMAND = "bold green"

# --- 3. FEATURED LIST ---
FEATURED_MANGAS = {
    "one-piece", "bleach", "naruto", "dragon-ball", "hunter-x-hunter", 
    "jujutsu-kaisen", "chainsaw-man", "demon-slayer-kimetsu-no-yaiba", "my-hero-academia",
    "berserk", "vagabond", "vinland-saga", "kingdom", "monster", 
    "20th-century-boys", "oyasumi-punpun", "tokyo-ghoul", "gantz",
    "one-punch-man", "spy-x-family", "blue-lock", "dandadan", 
    "sakamoto-days", "frieren-at-the-funeral"
}

# --- 4. CLI Group ---
@click.group()
@click.version_option(version=VERSION)
def cli():
    """
    [bold cyan]🐇 YOMI CLI[/] - [italic white]The Universal Hybrid-Engine Manga Downloader[/]
    """
    pass

@click.command()
def api():
    """Starts the Yomi API Bridge for external apps (like Flutter)"""
    from .api import start_api
    console.print("[bold magenta]🚀 Yomi API Bridge starting on http://127.0.0.1:8000[/]")
    start_api()

# cli.py'deki ana gruba ekle:
cli.add_command(api)


# --- 5. Download Command ---
@cli.command()
@click.option('-u', '--url', required=True, help="Target URL or Manga Name (Slug).")
@click.option('-o', '--out', default='downloads', show_default=True, help="Output Directory.")
@click.option('-w', '--workers', default=8, show_default=True, help="Concurrent Download Limit.")
@click.option('-f', '--format', default='folder', type=click.Choice(['folder', 'pdf', 'cbz'], case_sensitive=False), help="Output Format.")
@click.option('-r', '--range', 'chapter_range', default=None, help="Chapter Range (e.g. 1-10).")
@click.option('-p', '--proxy', default=None, help="Proxy URL.")
@click.option('--debug/--no-debug', default=False, help="Enable verbose logs.")
def download(url, out, workers, format, chapter_range, proxy, debug):
    """
    📥 [bold]Download Manga[/] - [dim]Initialize the extraction engine.[/]
    """
    if debug:
        logger.setLevel("DEBUG")
    
    # --- MISSION BRIEFING ---
    info_text = Text()
    info_text.append(f"🎯 Target:   ", style="bold cyan")
    info_text.append(f"{url}\n", style="white")
    info_text.append(f"📂 Output:   ", style="bold yellow")
    info_text.append(f"{out}\n", style="white")
    info_text.append(f"⚡ Workers:  ", style="bold green")
    info_text.append(f"{workers} Threads\n", style="white")
    info_text.append(f"📦 Format:   ", style="bold magenta")
    info_text.append(f"{format.upper()}", style="white")

    if chapter_range:
        info_text.append(f"\nHash Range: {chapter_range}", style="dim italic")

    panel = Panel(
        info_text,
        title=f"[bold green]🚀 {APP_NAME} INITIALIZED[/]",
        subtitle=f"[dim]v{VERSION}[/]",
        border_style="green",
        expand=False
    )
    console.print(panel)

    # --- EXECUTION ---
    start_time = time.time()
    
    try:
        with console.status("[bold cyan]Establishing Uplink... Resolving Target...[/]", spinner="dots12"):
             # Simulating check time / waiting for remote db
             time.sleep(0.5)

        console.rule("[bold cyan]Extraction Matrix Active[/]")
        
        # --- ENGINE START ---
        engine = YomiCore(output_dir=out, workers=workers, debug=debug, format=format, proxy=proxy)
        engine.download_manga(url, chapter_range=chapter_range)
        # --- ENGINE END ---

        end_time = time.time()
        elapsed = end_time - start_time
        time_str = str(timedelta(seconds=int(elapsed)))

        # --- DEBRIEF ---
        stats_grid = Table.grid(expand=True, padding=(0, 2))
        stats_grid.add_column(style="bold white")
        stats_grid.add_column(justify="right", style="bold green")
        
        stats_grid.add_row("⏱️  Total Duration:", time_str)
        stats_grid.add_row("📦  Final Format:", format.upper())
        stats_grid.add_row("📂  Destination:", os.path.abspath(out))
        stats_grid.add_row("✅  Mission Status:", "SUCCESS")
        
        console.print("")
        console.print(Panel(
            stats_grid,
            title="[bold green]✨ MISSION DEBRIEF ✨[/]",
            subtitle="[dim]System Report[/]",
            border_style="green",
            expand=True
        ))
        
    except KeyboardInterrupt:
        console.print("\n[bold red]⚠️  MISSION ABORTED BY USER[/]")
    except Exception as e:
        console.print(Panel(
            f"[bold red]❌ CRITICAL SYSTEM FAILURE[/]\n{str(e)}",
            title="[bold red]ERROR[/]",
            border_style="red",
            expand=True
        ))
        if debug:
            logger.exception("Traceback:")

# --- 6. Available Command ---
@cli.command()
@click.option('-s', '--search', help="Search for a manga.")
@click.option('--all', 'show_all', is_flag=True, help="Show entire database.")
def available(search, show_all):
    """
    🌍 [bold]Library Grid[/] - [dim]Browse the supported collection.[/]
    """
    # Initialize engine just to load config (Remote or Local)
    # This ensures CLI sees the same DB as the downloader
    engine = YomiCore(workers=1) 
    sites = engine.sites_config
    
    if not sites:
        console.print("[bold red]❌ Error:[/bold red] No site configuration loaded.")
        return

    # --- SEARCH MODE ---
    if search:
        search = search.lower().strip()
        results = []
        for key, data in sites.items():
            score = 0
            name = data.get('name', key).lower()
            if search == key: score = 100
            elif search in key: score = 50
            elif search in name: score = 40
            
            if score > 0:
                results.append((score, key, data))
        
        results.sort(key=lambda x: x[0], reverse=True)
        
        if not results:
            console.print(f"[red]No signals found for '{search}'.[/]")
            return

        table = Table(title=f"🔎 Search Results: '{search}'", box=box.SIMPLE, border_style="cyan", show_header=True)
        table.add_column("Command Key", style="bold cyan")
        table.add_column("Official Name", style="white")
        table.add_column("Source Domain", style="dim")
        
        for score, key, data in results:
            table.add_row(key, data.get('name', key.title()), data.get('base_domain', 'Unknown'))
        console.print(table)
        return

    # --- GRID MODE ---
    if show_all:
        display_keys = sorted(list(sites.keys()))
        title = f"📚 Full Archive ({len(sites)} Series)"
        color_style = "blue"
    else:
        # Featured Logic
        display_keys = [k for k in FEATURED_MANGAS if k in sites]
        
        # Fill to 24 if needed
        if len(display_keys) < 24 and len(sites) >= 24:
            extras = [k for k in list(sites.keys()) if k not in display_keys][:24 - len(display_keys)]
            display_keys.extend(extras)
            
        display_keys = sorted(display_keys)
        title = f"🔥 Trending Collection"
        color_style = "magenta"

    console.rule(f"[{color_style}]{title}[/]")

    # Layout Engine
    width = console.size.width
    card_width = 30 
    columns_count = max(1, width // card_width)
    
    layout_table = Table(box=None, show_header=False, padding=(0, 1), expand=True)
    for _ in range(columns_count):
        layout_table.add_column(ratio=1)

    for i in range(0, len(display_keys), columns_count):
        row_keys = display_keys[i:i + columns_count]
        row_renderables = []

        for key in row_keys:
            data = sites.get(key, {})
            name = data.get('name', key.replace("-", " ").title())
            domain = data.get('base_domain', 'Unknown')
            
            safe_len = int(width / columns_count) - 6
            if safe_len < 15: safe_len = 15
            
            if len(name) > safe_len: name = name[:safe_len-3] + "..."
            if len(domain) > safe_len: domain = domain[:safe_len-3] + "..."

            p = Panel(
                f"[bold cyan]{name}[/]\n[dim white]{domain}[/]",
                border_style=f"dim {color_style}",
                expand=True
            )
            row_renderables.append(p)

        while len(row_renderables) < columns_count:
            row_renderables.append(Text(""))

        layout_table.add_row(*row_renderables)
        layout_table.add_row(*[Text("") for _ in range(columns_count)])

    console.print(layout_table)
    
    if not show_all and len(sites) > len(display_keys):
        remaining = len(sites) - len(display_keys)
        console.print(f"\n[dim italic]...and {remaining} more series hidden. Use [bold cyan]--all[/] to view.[/]", justify="center")

if __name__ == '__main__':
    cli()