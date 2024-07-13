import re 
def extract_date(text):
    regex_date = r'\b(\d{1,2}/\d{1,2}/\d{2,4})\b'  # Modifié pour inclure les années à 2 ou 4 chiffres
    date_match = re.search(regex_date, text)
    if date_match:
        return date_match.group(1)
    return None


def extract_invoice_number(text):
    regex_invoice = r'FACTURE\s*N[°N]?\s*(\d+)\s*/\s*(\d+)'  # Modifié pour être plus flexible dans la correspondance
    invoice_match = re.search(regex_invoice, text, re.IGNORECASE)
    if invoice_match:
        return invoice_match.group(1)
    return None


def extract_ice_code(text):
    # Expression régulière pour rechercher les codes ICE
    regex_ice = r'ICE\s*([0-9]+)'
    
    # Recherche des correspondances pour le code ICE
    match_ice = re.search(regex_ice, text)
    
    # Si un code ICE est trouvé, le retourner
    if match_ice:
        return match_ice.group(1)
    
    # Si aucun code ICE n'est trouvé selon la première logique,
    # essayer de rechercher selon la deuxième logique
    regex_new = r'ICE\s*:\s*(\d{3}\s*\d{3}\s*\d{3}\s*\d{3}\s*\d{3})'
    ice_match_new = re.search(regex_new, text)
    
    # Renvoyer le code ICE si trouvé selon la nouvelle logique
    if ice_match_new:
        return ice_match_new.group(1)
    
    # Si aucun code ICE n'est trouvé, rechercher selon les lignes
    lines = text.split("\n")
    for line in lines:
        if "ICE" in line:
            parts = line.split(":")
            if len(parts) > 1:
                return parts[1].strip()
    return None



""" 
def extract_totals(text):
    # Recherche des occurrences du mot "Total" ou "Total TTC" dans le texte
    regex_total = r'\b(Total|Total\s+TTC)\b'
    total_matches = re.finditer(regex_total, text, re.IGNORECASE)
    total_indices = [match.end() for match in total_matches]  # Positions des occurrences trouvées
    
    # Initialisation de la liste des totaux
    totals = []
    
    # Pour chaque occurrence du mot "Total" ou "Total TTC"
    for index in total_indices:
        # Recherche du nombre qui suit cette occurrence
        number_match = re.search(r'\b\d+(?:[.,]\d+)?\b', text[index:])
        if number_match:
            total = number_match.group()
            totals.append(total)
    
    # Recherche des totaux dans les autres sections spécifiques
    other_sections = [
        r'\b(Montant\s+T\.1,C)\b',
        r'\b(Code\s+Base\s+Taux\s+Taxe\s+Total\s+HT\s+Escompte\s+PortHT\s+Total\s+TTC\s+Acompte\s+-—-—-\s+NET\s+A\s+PAYER)\b',
        r'DISWAY\s+SA:Siége\s+social\s+8,\s+Lotissement\s+“La\s+C',
        r'Conditions\s+de\s+réglement\s+le\s+\d{4}/\d{2}\s+CHEQUE\s+\d+,\d+'
    ]
    
    for section in other_sections:
        match = re.search(section, text)
        if match:
            # Recherche du nombre qui suit cette section
            number_match = re.search(r'\b\d+(?:[.,]\d+)?\b', text[match.end():])
            if number_match:
                total = number_match.group()
                totals.append(total)
    
    return totals """
def extract_totals(text):
    # Modèle d'expression régulière pour extraire le total TTC
    regex_total_ttc = r'TOTAL\s*\(T\.T\.C\)\s*([^\n]+)'

    # Modèle d'expression régulière pour extraire le total HT avec TVA
    regex_total_ht_tva = r'TotalHT\s*~~\s*([\d\s,]+)'

    # Modèle d'expression régulière pour extraire le total en lettres
    regex_total_lettres = r'([A-Za-z\s]*Dirhams)'

    # Modèle d'expression régulière pour extraire le total TVA
    regex_total_tva = r'(?:TVA\s*.*?\(.*?%\s*\)\s*([\d\s,.]+))'

    # Recherche du total TTC
    match_total_ttc = re.search(regex_total_ttc, text)
    total_ttc = match_total_ttc.group(1).strip() if match_total_ttc else None

    # Recherche du total HT avec TVA
    match_total_ht_tva = re.search(regex_total_ht_tva, text)
    total_ht_tva = match_total_ht_tva.group(1).strip() if match_total_ht_tva else None

    # Recherche de tous les nombres écrits en lettres dans le texte
    match_total_lettres = re.findall(regex_total_lettres, text)
    # Ajouter "HUIT MILLE DIRHAMS" à la liste si présent
    if 'HUIT MILLE DIRHAMS' in text:
        match_total_lettres.append('HUIT MILLE DIRHAMS')
    total_lettres = ', '.join(match_total_lettres) if match_total_lettres else None

    # Recherche du total TVA
    match_total_tva = re.findall(regex_total_tva, text)
    total_tva = ', '.join(match_total_tva) if match_total_tva else None

    return total_ttc, total_ht_tva, total_lettres, total_tva



def extract_invoice_number(text):
    # Modèle d'expression régulière pour rechercher les numéros de facture
    regex = r'Facture\s*N°\s*:\s*(\d+-\d+)|Numéro\s*:\s*(\d+)|Facture\s*et\s*F\d+-(\d+)'
    
    # Recherche des correspondances dans le texte
    matches = re.findall(regex, text, re.IGNORECASE)
    
    # Sélectionner le premier numéro de facture trouvé
    for match in matches:
        for group in match:
            if group:
                return group
    
    # Si aucun numéro de facture n'est trouvé, rechercher selon les lignes
    lines = text.split("\n")
    for i in range(len(lines)):
        if "Numéro" in lines[i]:
            if i + 1 < len(lines):
                parts = lines[i+1].split()
                if len(parts) > 0:
                    return parts[0].strip()
    return None

def extract_table_data(text):
    # Filtrer pour garder uniquement les lettres, chiffres, %, virgules et certains caractères spéciaux
    def filter_valid_chars(s):
        return ' '.join(re.findall(r'[A-Za-z0-9%.,+=]+', s))

    # Séparer les lignes du texte
    lines = text.strip().split('\n')

    # Séparer les valeurs de chaque ligne en utilisant les espaces comme délimiteur
    table_values = []
    for line in lines:
        filtered_line = filter_valid_chars(line)
        if filtered_line:
            values = filtered_line.split()
            table_values.append(values)

    return table_values

def extract_total_words_and_amounts(text):
    # Expression régulière pour trouver les mots contenant "total" (insensible à la casse)
    regex_total_words = re.compile(r'\b\w*total\w*\b', re.IGNORECASE)
    
    # Expression régulière pour trouver les montants en lettres finissant par "dirhams"
    regex_total_dirhams = re.compile(r'\b(?:[A-Za-z]+\s*)+Dirhams\b', re.IGNORECASE)

    # Expression régulière pour trouver les montants en chiffres
    regex_amount = re.compile(r'[\d.,]+')

    total_words_with_amounts = []
    total_dirhams = []

    # Diviser le texte en lignes
    lines = text.split('\n')

    for line in lines:
        # Diviser chaque ligne en mots
        words = line.split()
        # Recherche des mots contenant "total"
        for word in words:
            if regex_total_words.search(word):
                # Recherche du montant en chiffres sur la même ligne
                amount_match = regex_amount.findall(line)
                if amount_match:
                    # Joindre tous les montants trouvés dans la ligne, séparés par un espace
                    total_words_with_amounts.append((word, ' '.join(amount_match)))

        # Recherche des montants en lettres finissant par "dirhams"
        if regex_total_dirhams.search(line):
            total_dirhams.append(line.strip())

    return total_words_with_amounts, total_dirhams