## LISEZ-MOI
-----------------------

Ce programme permet de defusionner, reorganiser, et refusionner des documents pdf et excel de facturation par groupement. 


1. Ce programme a été testé avec Python 3.12.4. Installer cette version de Python sur le système
2. Installer les dépendances indiquées dans le fichier `requirements.txt`. En utilisant pip en ligne de commande, cela donne : 

`
pip3 install -r requirements.txt
`

3. Noter le chemin d'accès vers le dossier qui contient toutes les documents PDF de facturations (unitaires et globales), ainsi que le fichier `fichier details.xlsx` qui permet de connaitre les correspondances entre groupement et PDL.

4. Ouvrir le fichier main.py et y insérer le chemin d'accès vers le dossier (à la place de `./test_data/`)
5. Executer le programme avec la bonne version de l'interpreteur python (ici python3): 

`
python3 main.py
`

6. Récupérer les résultats dans le sous-dossier `results/` situé dans le dossier contenant les données traitées. A noter que le programme crée également un dossier `extract/`, qui contient le cas échéant les factures unitaires pour lequel le programme n'a pas trouvé de correspondance. Il crée aussi un dossier `merge/` qui contient tous les documents PDF et excel correspondant à un groupe et avant la fuison. 

Si vous rencontrez des problèmes dans l'execution du programme, vous pouvez me contacter à l'adresse suivante: thomas.puiseux@gmail.com
