import click
import logging
import json
import os
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table
from .core import YomiCore

# Setup Fancy Console
console = Console()
logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(console=console, rich_tracebacks=True)]
)
logger = logging.getLogger("YomiCLI")

@click.group()
def cli():
    """YOMI - Rabbit Speed Manga Downloader 🐇"""
    pass

@cli.command()
@click.option('-u', '--url', required=True, help='Link to the manga')
@click.option('-o', '--out', default='downloads', help='Output folder')
@click.option('-w', '--workers', default=8, help='Download threads')
@click.option('-f', '--format', default='folder', type=click.Choice(['folder', 'pdf', 'cbz']), help='Output format')
@click.option('-r', '--range', default=None, help='Chapter Range (e.g., "1-100")')
@click.option('-p', '--proxy', default=None, help='Proxy URL (http://user:pass@ip:port)')
@click.option('--debug/--no-debug', default=False, help='Enable developer logs')
def download(url, out, workers, format, range, proxy, debug):
    """Download manga from any supported URL."""
    
    if debug:
        logger.setLevel("DEBUG")
        console.print("[bold red]DEBUG MODE ACTIVE[/bold red]")

    console.print(f"[bold green]STARTING Yomi...[/bold green]")
    
    # Show user what settings are active
    if range:
        console.print(f"🎯 Range: [yellow]{range}[/yellow]")
    if proxy:
        console.print(f"🛡️ Proxy: [yellow]Enabled[/yellow]")
    if format != 'folder':
        console.print(f"📦 Format: [cyan]{format.upper()}[/cyan]")
    
    try:
        # Initialize the Engine
        engine = YomiCore(
            output_dir=out, 
            workers=workers, 
            debug=debug, 
            format=format, 
            proxy=proxy
        )
        
        # Start Downloading
        engine.download_manga(url, chapter_range=range)
        
        console.print("[bold green]✅ ALL DONE! Enjoy your manga.[/bold green]")
        
    except Exception as e:
        console.print(f"[bold red]❌ Error:[/bold red] {e}")

@cli.command()
def available():
    """List verified sites from sites.json"""
    table = Table(title="Community Verified Sites")
    table.add_column("Site Name", style="cyan")
    table.add_column("Target / Pattern", style="green")
    table.add_column("Type", style="magenta")

    # DOĞRU YOL: yomi klasörünün içindeki sites.json'ı bul
    json_path = os.path.join(os.path.dirname(__file__), "sites.json")
    
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r') as f:
                sites = json.load(f)
                for key, data in sites.items():
                    # Dinamik siteler için pattern'i, diğerleri için URL'yi göster
                    target = data.get('base_domain') if 'base_domain' in data else data.get('url')
                    name = data.get('name', key.capitalize())
                    engine_type = data.get('type', 'static')
                    
                    table.add_row(name, target, engine_type)
        except json.JSONDecodeError:
             table.add_row("Error", "sites.json corrupted", "ERROR")
    else:
        console.print("[red]sites.json not found![/red]")
    
    console.print(table)
if __name__ == '__main__':
    cli()