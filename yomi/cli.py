import os
import json
import logging
import rich_click as click
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table
from rich import box  # <-- Tablo kenarlıkları için

# --- Core Module ---
from .core import YomiCore

# --- 1. Console & Logging Setup ---
console = Console()
logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(console=console, rich_tracebacks=True, markup=True)]
)
logger = logging.getLogger("YomiCLI")

# --- 2. Rich Click Configuration ---
click.rich_click.USE_RICH_MARKUP = True
click.rich_click.SHOW_ARGUMENTS = True
click.rich_click.GROUP_ARGUMENTS_OPTIONS = True
click.rich_click.STYLE_ERRORS_SUGGESTION = "magenta italic"
click.rich_click.ERRORS_SUGGESTION = "Did you mean this?"
click.rich_click.SHOW_METAVARS_COLUMN = False
click.rich_click.APPEND_METAVARS_HELP = True

# --- 3. CLI Group ---
@click.group()
def cli():
    """
    [bold cyan]🐇 YOMI CLI v0.3[/] - [italic white]Rabbit Speed Manga Downloader[/]

    [green]Yomi[/] is a next-gen tool that bypasses protected sites, uses smart caching, and archives manga into [yellow]PDF/CBZ[/] formats.
    """
    pass

# --- 4. Download Command ---
@cli.command()
@click.option(
    '-u', '--url', 
    required=True, 
    help="[bold yellow]Target URL[/] or Site Key. [dim]Ex: 'bleach' or 'https://site.com/manga/name'[/]"
)
@click.option(
    '-o', '--out', 
    default='downloads', 
    show_default=True, 
    help="Output Directory. [dim]Ex: 'C:/Manga' or 'my_downloads'[/]"
)
@click.option(
    '-w', '--workers', 
    default=8, 
    show_default=True, 
    help="Concurrent Download Limit. [dim]Rec: 8-16 for speed, 4 for stability.[/]"
)
@click.option(
    '-f', '--format', 
    default='folder', 
    show_default=True, 
    type=click.Choice(['folder', 'pdf', 'cbz'], case_sensitive=False), 
    help="Output Format. [dim]Use 'cbz' for Kavita/Komga, 'pdf' for mobile.[/]"
)
@click.option(
    '-r', '--range', 'chapter_range', 
    default=None, 
    help="Chapter Range. [dim]Ex: '1-10' (Range), '5' (Single), '100-' (From 100 to end)[/]"
)
@click.option(
    '-p', '--proxy', 
    default=None, 
    help="Proxy URL. [dim]Ex: 'http://user:pass@1.2.3.4:8080'[/]"
)
@click.option(
    '--debug/--no-debug', 
    default=False, 
    help="Enable Developer Mode. [dim]Shows verbose connection logs.[/]"
)
def download(url, out, workers, format, chapter_range, proxy, debug):
    """
    📥 [bold]Download Manga[/]
    
    Downloads, formats, and archives manga from the specified URL or verified site.
    """
    
    if debug:
        logger.setLevel("DEBUG")
        console.print("[bold red]🐛 DEBUG MODE ACTIVE[/bold red]")

    console.print(f"[bold green]🐇 STARTING Yomi...[/bold green]")
    
    if chapter_range:
        console.print(f"🎯 Range: [yellow]{chapter_range}[/yellow]")
    if proxy:
        console.print(f"🛡️ Proxy: [yellow]Enabled[/yellow]")
    if format != 'folder':
        console.print(f"📦 Format: [cyan]{format.upper()}[/cyan]")
    
    try:
        engine = YomiCore(output_dir=out, workers=workers, debug=debug, format=format, proxy=proxy)
        engine.download_manga(url, chapter_range=chapter_range)
        console.print("[bold green]✅ ALL DONE! Enjoy your manga.[/bold green]")
        
    except Exception as e:
        console.print(f"[bold red]❌ Error:[/bold red] {e}")
        if debug:
            logger.exception("Traceback:")

# --- 5. Available Command (Updated) ---
@cli.command()
@click.option(
    '-s', '--search', 
    help="Filter sites by name. [dim]Ex: 'piece', 'leveling', 'asura'[/]"
)
def available(search):
    """
    🌍 [bold]Supported Sites[/]
    
    Lists verified sites from sites.json. Can be filtered with --search.
    """
    # Rich Table Upgrade: Rounded Corners & Styles
    table = Table(
        title="[bold cyan]Community Verified Sites[/]",
        box=box.ROUNDED,
        header_style="bold white on blue",
        border_style="blue"
    )
    table.add_column("Site Name", style="cyan bold", no_wrap=True)
    table.add_column("Target / Base Domain", style="green")
    table.add_column("Type", style="magenta", justify="center")

    json_path = os.path.join(os.path.dirname(__file__), "sites.json")
    
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                sites = json.load(f)
                
                count = 0
                # Sort and Filter
                for key, data in sorted(sites.items()):
                    name = data.get('name', key.replace('-', ' ').title())
                    
                    # Filter Logic
                    if search:
                        if search.lower() not in key.lower() and search.lower() not in name.lower():
                            continue

                    target = data.get('base_domain') if 'base_domain' in data else data.get('url', 'Unknown')
                    engine_type = data.get('type', 'static').upper()
                    
                    # Icons for types
                    type_str = f"⚡ {engine_type}" if engine_type == "DYNAMIC" else f"🔒 {engine_type}"
                    
                    table.add_row(name, target, type_str)
                    count += 1
                    
            console.print(table)
            
            if search:
                 console.print(f"\n[dim]Found {count} sites matching '{search}'.[/dim]")
            else:
                 console.print(f"\n[dim]Total {len(sites)} sites registered.[/dim]")

        except json.JSONDecodeError:
             console.print("[bold red]❌ Error:[/bold red] sites.json file is corrupted!")
    else:
        console.print("[bold red]❌ Error:[/bold red] sites.json file not found!")

if __name__ == '__main__':
    cli()