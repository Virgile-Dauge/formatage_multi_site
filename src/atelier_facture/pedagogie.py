from rich.tree import Tree
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table

from pathlib import Path
from pandas import DataFrame

def afficher_arborescence_travail(console:Console, p:Path, ip:Path, ep:Path, fp:Path):

    # Affichage de l'arborescence statique du répertoire de travail
    tree = Tree(f"📁 {p}")
    extrait = tree.add(f"[bold blue]{ip.name}[/bold blue]")
    extrait.add("[green]Fichiers extraits depuis le Zip[/green]")
    
    enrichi = tree.add(f"[bold blue]{ep.name}[/bold blue]")
    enrichi.add("[green]Fichiers générés (tableaux, groupements enrichis, groupement mono)[/green]")
    
    facturx = tree.add(f"[bold blue]{fp.name}[/bold blue]")
    facturx.add("[green]XMLs et PDFs Factur-X générés[/green]")

    tree.add("[green]todo.csv[/green] (consignes extraites du Zip)")
    tree.add("[green]bt.csv[/green] (données Factur-X extraites du Zip)")
    tree.add("[green]todo_enrichi.csv[/green] (consignes enrichies des chemins des fichiers enrichis créés)")
    
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