from functools import wraps
from rich.progress import Progress, TextColumn, BarColumn, TaskProgressColumn
from rich.console import Console
from typing import Callable, Any
from rich.tree import Tree
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from typing import Callable
from pathlib import Path
from pandas import DataFrame

def afficher_arborescence_travail(console:Console, p:Path, ip:Path, ep:Path, fp:Path):

    # Affichage de l'arborescence statique du répertoire de travail
    tree = Tree(f"📁 {p}")
    extrait = tree.add(f"[bold blue]{ip.name}[/bold blue]")
    extrait.add("[green]Fichiers extraits depuis le Zip[/green]")
    extrait.add("[green]consignes.csv[/green] (consignes extraites du Zip)")
    extrait.add("[green]facturx.csv[/green] (données Factur-X extraites du Zip)")
    extrait.add("[green]extrait.csv[/green] (récap des données extraites du zip)")
    
    enrichi = tree.add(f"[bold blue]{ep.name}[/bold blue]")
    enrichi.add("[green]Fichiers générés (tableaux, groupements enrichis, groupement mono)[/green]")
    
    facturx = tree.add(f"[bold blue]{fp.name}[/bold blue]")
    facturx.add("[green]XMLs et PDFs Factur-X générés[/green]")

    tree.add("[green]consignes_consolidees.csv[/green] (consignes enrichies des chemins des fichiers enrichis créés)")
    tree.add("[green]facturx_consolidees.csv[/green] (consignes enrichies des chemins des fichiers enrichis créés)")
    
    console.print(tree)
    console.print("\n[italic]Explication de l'arborescence :[/italic]")
    console.print("• Les [bold blue]dossiers[/bold blue] sont affichés en bleu")
    console.print("• Les [green]fichiers[/green] sont affichées en vert")
    console.print("• Cette structure représente l'organisation générale")
    console.print()

def dataframe_to_table(df: DataFrame, title:str) -> Table:
    table = Table(title=title)
    
    # Ajouter les colonnes que vous voulez afficher
    for column in df.columns:
        table.add_column(column)
    
    # Ajouter les lignes
    for _, row in df.iterrows():
        table.add_row(*[str(value) for value in row])
    return table

def etat_avancement(console: Console, df: DataFrame, ip:Path, ep:Path, fp:Path):
    # Extraction
    
    console.print(f"Extraction des fichiers") 
    types = ['mono', 'pdl', 'groupement']
    
    for type in types:
        todo = df[df['type'] == type]
        total_count = len(todo)

        if total_count == 0:
            console.print(f"Type {type}: Aucun élément trouvé")
            continue
        extracted_count = todo['fichier_extrait'].notna().sum()
        missing_count = total_count - extracted_count
        
        console.print(f"Type {type}:")
        console.print(f"  Total: {total_count}")
        console.print(f"  Extraits: {extracted_count}")
        console.print(f"  Pourcentage extrait: {(extracted_count/total_count)*100:.2f}%")
        
        if missing_count > 0:
            console.print(f"  Manquants: {missing_count}")
            missing_df = todo[todo['fichier_extrait'].isna()]

            
            console.print(dataframe_to_table(missing_df, f"[red]Éléments manquants pour le type [bold]{type}[/bold][/red]"))
        
        console.print()  # Ligne vide pour la lisibilité

def rapport_extraction(attendu: DataFrame, extrait:DataFrame, console: Console|None=None):
    if console is None:
        console = Console()

    total_fichiers = len(extrait)
    factures_unitaires = extrait['pdl'].notna().sum()
    factures_unitaires_attendues = attendu['pdl'].notna().sum()
    factures_groupees = extrait['groupement'].notna().sum()
    console.print(f"Nombre total de fichiers extraits : {total_fichiers}")
    console.print(f"Nombre de factures unitaires : {factures_unitaires}/{factures_unitaires_attendues} ({factures_unitaires/factures_unitaires_attendues*100:.2f}%)")
    console.print(f"Nombre de factures groupées : {factures_groupees}")
    console.print(attendu)
    # Affichage des valeurs uniques des dates
    console.print("\nDates uniques :")
    dates_uniques = extrait['date'].unique()
    for date in sorted(dates_uniques):
        console.print(f"- {date}")

    # TODO: Chercher les duplicatas afficher que les id uniques
    console.print("\nID uniques avec duplicatas :")
    duplicatas = extrait[extrait.duplicated(subset=['id'], keep=False)]

def with_progress_bar(description: str = "Processing..."):
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args, **kwargs):
            console = Console()
            progress = Progress(
                TextColumn("[bold blue]{task.description}", justify="right"),
                BarColumn(bar_width=None),
                TaskProgressColumn(),
                console=console,
            )

            with progress:
                task = progress.add_task(f"[cyan]{description}", total=None)

                def progress_callback(current: int, total: int):
                    if progress.tasks[task].total != total:
                        progress.update(task, total=total)
                    progress.update(task, completed=current)

                result = func(*args, **kwargs, progress_callback=progress_callback)

            return result

        return wrapper

    return decorator