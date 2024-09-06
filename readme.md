## Documentation du Programme Complet

### Description
Ce programme permet de défusionner, réorganiser, et refusionner des documents PDF et Excel de facturation par groupement. Il a été conçu pour traiter des factures unitaires et globales, et pour générer des rapports consolidés par groupement.

### Prérequis
1. **Python Version**: Ce programme a été testé avec Python 3.12.4. Assurez-vous d'installer cette version de Python sur votre système.
2. **Dépendances**: Installez les dépendances listées dans le fichier `requirements.txt`. Utilisez la commande suivante pour les installer :
    ```
    pip3 install -r requirements.txt
    ```

### Instructions d'Utilisation
1. **Préparation des Données**:
    - Placez tous les documents PDF de facturation (unitaires et globales) ainsi que le fichier `factures details.xlsx` dans un dossier. le `xlsx` doit être à la racine du dossier, le reste n'importe pas.
    - Notez le chemin d'accès vers ce dossier.

2. **Exécution**:
    - Exécutez le programme avec la commande suivante :
    ```
    python3 main.py <chemin_du_dossier_de_données>
    ```

3. **Résultats**:

    Voici l'architecture des résultats après exécution du programme:
    ```
    data_dir/
    ├── input
    │   ├── dossiers_imbriques
    │   ├── dossiers_imbriques_en_rab
    │   ├── dossiers_peu_importe
    │   └── lien.xslx
    └── output
        ├── extract
        │   ├── group
        │   └── indiv
        ├── merge
        │   ├── GROUPEMENT1
        │   └── GROUPEMENT2
        └── results
    ```
    - Les factures de groupement consolidées (synthèse + tableau + factures individuelles) sont générés dans le sous-dossier `results/`
    - Le programme crée également un dossier `extract/` dans lequel sont extraites toutes les factures , 
    - A des fin de débuggage le dossier `merge/` pour les documents PDF et Excel avant fusion.

### Fonctionnalités
- **Défusionner les PDF**: Le programme divise les fichiers PDF en fonction des informations extraites via des expressions régulières.
- **Génération des tableaux**: Le fichier Excel est divisé par groupe et sert de base à la création de la page tableau récapitulatif de chaque groupement. 
- **Fusionner les PDF**: Les fichiers PDF sont fusionnés par groupement, en incluant les factures globales et les tableaux récapitulatifs.
- **Compression des PDF**: Les fichiers PDF fusionnés sont compressés pour réduire leur taille.

